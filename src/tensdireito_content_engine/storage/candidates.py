"""Registo persistente de candidatos (fase 2a; especificação das fases 2–4, §1, §2 e §1.7).

Um `candidate` é uma notícia, identificada por `url_key`; cada endpoint que a encontrou
fica em `candidate_discovery`. Só `transition()` muda o estado de um candidato: faz um
`UPDATE … WHERE id = ? AND state = ?` (compare-and-set) e, se uma linha mudou, grava a
linha de `candidate_transition` na mesma transacção. Transições fora de `ALLOWED` levantam
erro antes do SQL.

Na fase 2a, o estado reflecte a decisão da fase 1 (DEC-063) sem a alterar: os rascunhos
continuam a ser decididos por `daily.py`; este módulo só regista o que aconteceu.
"""

import sqlite3
from collections import defaultdict
from collections.abc import Collection, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from tensdireito_content_engine.storage.database import to_utc_iso, transaction
from tensdireito_content_engine.storage.errors import StorageError
from tensdireito_content_engine.storage.interfaces import Connection
from tensdireito_content_engine.storage.schema import open_existing_database

DISCOVERED = "descoberto"
OUT_OF_DAY = "fora_do_dia"
ARCHIVED = "arquivado"
GROUPED = "agrupado"
DRAFTED = "rascunho"
IN_GROUP = "no_grupo"

STATES = frozenset(
    {
        DISCOVERED,
        OUT_OF_DAY,
        ARCHIVED,
        "a_extrair",
        "extraido",
        "bloqueado",
        "a_classificar",
        "classificado",
        "descartado",
        "pendente_revisao",
        GROUPED,
        DRAFTED,
        IN_GROUP,
        "expirado",
    }
)

# §2 da especificação. `None` é a criação do candidato.
ALLOWED: dict[str | None, frozenset[str]] = {
    None: frozenset({DISCOVERED}),
    DISCOVERED: frozenset({OUT_OF_DAY, ARCHIVED, "a_extrair", GROUPED}),
    "a_extrair": frozenset({"extraido", "a_extrair", "bloqueado", "expirado"}),
    "extraido": frozenset({"a_classificar"}),
    "a_classificar": frozenset({"classificado", "a_classificar", "pendente_revisao", "expirado"}),
    "classificado": frozenset({"descartado", "pendente_revisao", GROUPED}),
    "pendente_revisao": frozenset({"expirado"}),
    GROUPED: frozenset({DRAFTED, IN_GROUP}),
    ARCHIVED: frozenset({DISCOVERED}),
    "descartado": frozenset({DISCOVERED}),
}

METHODS = frozenset({"rss", "news_sitemap", "search", "html_list", "json_api", "open_data"})
PUBLISHED_SOURCES = frozenset({"sitemap", "feed", "page", "url", "first_seen", "none"})
PRIORITIES = frozenset({"alta", "rever", "baixa"})


class TransitionError(StorageError):
    """Transição que a máquina de estados não permite."""


@dataclass(frozen=True, slots=True)
class Observation:
    """Uma captura (`raw_item`) vista neste run e o que a fase 1 decidiu sobre ela."""

    raw_item_id: int
    endpoint_id: str
    method: str
    url_key: str
    url: str
    title: str
    summary: str | None
    source_id: str | None
    source_tier: str
    published_at: datetime | None
    published_at_source: str
    seen_at: datetime
    priority: str
    priority_reason: str
    # Destino na máquina de estados e motivo (ver `daily.candidate_target`).
    target: str
    target_reason: str
    # Para `no_grupo`: a captura que representa o grupo; `None` nos restantes.
    group_of_raw_item_id: int | None = None


@dataclass(frozen=True, slots=True)
class MethodStats:
    candidates: int = 0
    exclusive: int = 0
    new_discoveries: int = 0


@dataclass(frozen=True, slots=True)
class CandidateStats:
    observations: int = 0
    candidates: int = 0
    new_candidates: int = 0
    transitions: int = 0
    by_state: dict[str, int] = field(default_factory=dict)
    by_method: dict[str, MethodStats] = field(default_factory=dict)


def transition(
    conn: Connection,
    candidate_id: int,
    expected_state: str,
    new_state: str,
    reason: str,
    run_id: int | None,
    at: datetime,
) -> bool:
    """Muda o estado se ainda for `expected_state`; grava a transição. Devolve se mudou.

    Tem de ser chamada dentro de uma transacção: o `UPDATE` e o `INSERT` ficam juntos.
    """
    if new_state not in ALLOWED.get(expected_state, frozenset()):
        raise TransitionError(f"transição não permitida: {expected_state} → {new_state}")
    if not reason.strip():
        raise TransitionError("uma transição precisa de motivo")
    stamp = to_utc_iso(at)
    cursor = conn.execute(
        "UPDATE candidate SET state = ?, updated_at = ? WHERE id = ? AND state = ?",
        (new_state, stamp, candidate_id, expected_state),
    )
    if cursor.rowcount != 1:
        return False
    conn.execute(
        "INSERT INTO candidate_transition (candidate_id, from_state, to_state, reason, run_id, at) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (candidate_id, expected_state, new_state, reason, run_id, stamp),
    )
    return True


def record_observations(
    path: Path,
    observations: Sequence[Observation],
    run_id: int | None,
    at: datetime,
) -> CandidateStats:
    """Cria/actualiza candidatos e descobertas e aplica as transições, numa transacção.

    Várias capturas com o mesmo `url_key` dão um só candidato; o destino que conta é o
    mais avançado entre elas (`_TARGET_RANK`). Os rascunhos já guardados para uma destas
    capturas ficam ligados ao candidato (`whatsapp_draft.candidate_id`).
    """
    _validate(observations)
    conn = open_existing_database(Path(path))
    try:
        with transaction(conn, "não foi possível registar candidatos"):
            return _record(conn, observations, run_id, at)
    finally:
        conn.close()


# Ordem de destinos quando várias capturas apontam para a mesma notícia.
_TARGET_RANK = {OUT_OF_DAY: 0, ARCHIVED: 1, DISCOVERED: 2, GROUPED: 3, IN_GROUP: 4, DRAFTED: 5}


def _validate(observations: Sequence[Observation]) -> None:
    for obs in observations:
        if obs.method not in METHODS:
            raise StorageError(f"método de descoberta desconhecido: {obs.method}")
        if obs.priority not in PRIORITIES:
            raise StorageError(f"prioridade desconhecida: {obs.priority}")
        if obs.published_at_source not in PUBLISHED_SOURCES:
            raise StorageError(f"origem de data desconhecida: {obs.published_at_source}")
        if obs.target not in _TARGET_RANK:
            raise StorageError(f"destino desconhecido: {obs.target}")


def _record(
    conn: Connection, observations: Sequence[Observation], run_id: int | None, at: datetime
) -> CandidateStats:
    stamp = to_utc_iso(at)
    by_key: dict[str, list[Observation]] = defaultdict(list)
    for obs in observations:
        by_key[obs.url_key].append(obs)

    candidate_of_raw: dict[int, int] = {}
    new_candidates = 0
    new_discoveries: dict[str, int] = defaultdict(int)
    best: dict[int, Observation] = {}
    for group in by_key.values():
        first = min(group, key=lambda o: (o.seen_at, o.raw_item_id))
        candidate_id, created = _upsert_candidate(conn, first, group, stamp, run_id)
        new_candidates += created
        for obs in group:
            candidate_of_raw[obs.raw_item_id] = candidate_id
            if _upsert_discovery(conn, candidate_id, obs):
                new_discoveries[obs.method] += 1
        best[candidate_id] = max(group, key=lambda o: (_TARGET_RANK[o.target], -o.raw_item_id))

    transitions = 0
    groups: dict[int, int] = {}
    # Representantes primeiro, para os membros encontrarem o grupo.
    ordered = sorted(best.items(), key=lambda item: item[1].target != DRAFTED)
    for candidate_id, obs in ordered:
        transitions += _apply_target(conn, candidate_id, obs, candidate_of_raw, groups, run_id, at)

    for obs in observations:
        conn.execute(
            "UPDATE whatsapp_draft SET candidate_id = ? "
            "WHERE raw_item_id = ? AND candidate_id IS NULL",
            (candidate_of_raw[obs.raw_item_id], obs.raw_item_id),
        )
    _link_documents(conn, best, candidate_of_raw)
    return CandidateStats(
        observations=len(observations),
        candidates=len(best),
        new_candidates=new_candidates,
        transitions=transitions,
        by_state=_states(conn, list(best)),
        by_method=_method_stats(conn, list(best), new_discoveries),
    )


def _upsert_candidate(
    conn: Connection,
    first: Observation,
    group: Sequence[Observation],
    stamp: str,
    run_id: int | None,
) -> tuple[int, bool]:
    row = conn.execute(
        "SELECT id, state FROM candidate WHERE url_key = ?", (first.url_key,)
    ).fetchone()
    last_seen = to_utc_iso(max(o.seen_at for o in group))
    if row is not None:
        candidate_id, state = int(row[0]), row[1]
        conn.execute(
            "UPDATE candidate SET last_seen_at = MAX(last_seen_at, ?), updated_at = ? WHERE id = ?",
            (last_seen, stamp, candidate_id),
        )
        if state == DISCOVERED:
            # Ainda sem decisão: a prioridade acompanha as regras em vigor.
            top = max(group, key=lambda o: (_TARGET_RANK[o.target], -o.raw_item_id))
            conn.execute(
                "UPDATE candidate SET priority = ?, priority_reason = ? WHERE id = ?",
                (top.priority, top.priority_reason, candidate_id),
            )
        return candidate_id, False
    top = max(group, key=lambda o: (_TARGET_RANK[o.target], -o.raw_item_id))
    cursor = conn.execute(
        "INSERT INTO candidate (url_key, url, title, summary, source_id, source_tier, "
        "published_at, published_at_source, first_seen_at, last_seen_at, priority, "
        "priority_reason, state, attempts, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?)",
        (
            first.url_key,
            first.url,
            first.title,
            first.summary,
            first.source_id,
            first.source_tier,
            to_utc_iso(first.published_at) if first.published_at else None,
            first.published_at_source,
            to_utc_iso(first.seen_at),
            last_seen,
            top.priority,
            top.priority_reason,
            DISCOVERED,
            stamp,
            stamp,
        ),
    )
    candidate_id = int(cursor.lastrowid)
    conn.execute(
        "INSERT INTO candidate_transition (candidate_id, from_state, to_state, reason, run_id, at) "
        "VALUES (?, NULL, ?, ?, ?, ?)",
        (candidate_id, DISCOVERED, f"descoberto por {first.endpoint_id}", run_id, stamp),
    )
    return candidate_id, True


def _upsert_discovery(conn: Connection, candidate_id: int, obs: Observation) -> bool:
    seen = to_utc_iso(obs.seen_at)
    row = conn.execute(
        "SELECT id FROM candidate_discovery WHERE candidate_id = ? AND endpoint_id = ?",
        (candidate_id, obs.endpoint_id),
    ).fetchone()
    if row is not None:
        # A captura mais recente substitui a anterior: `tde prune` apaga por idade.
        conn.execute(
            "UPDATE candidate_discovery SET raw_item_id = MAX(raw_item_id, ?), "
            "seen_at = MAX(seen_at, ?) WHERE id = ?",
            (obs.raw_item_id, seen, row[0]),
        )
        return False
    conn.execute(
        "INSERT INTO candidate_discovery "
        "(candidate_id, raw_item_id, endpoint_id, method, first_seen_at, seen_at) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (candidate_id, obs.raw_item_id, obs.endpoint_id, obs.method, seen, seen),
    )
    return True


def _apply_target(
    conn: Connection,
    candidate_id: int,
    obs: Observation,
    candidate_of_raw: dict[int, int],
    groups: dict[int, int],
    run_id: int | None,
    at: datetime,
) -> int:
    state = conn.execute("SELECT state FROM candidate WHERE id = ?", (candidate_id,)).fetchone()[0]
    if state != DISCOVERED or obs.target == DISCOVERED:
        # Já decidido num run anterior (estados terminais não são reavaliados na 2a),
        # ou ainda sem decisão (prioridade rever, à espera da fase 3).
        return 0
    if obs.target in (OUT_OF_DAY, ARCHIVED):
        return int(
            transition(conn, candidate_id, DISCOVERED, obs.target, obs.target_reason, run_id, at)
        )
    count = int(
        transition(conn, candidate_id, DISCOVERED, GROUPED, obs.priority_reason, run_id, at)
    )
    if obs.target == DRAFTED:
        group_id = _new_group(conn, obs.title, at)
        groups[candidate_id] = group_id
        _set_group(conn, candidate_id, group_id)
        count += transition(conn, candidate_id, GROUPED, DRAFTED, obs.target_reason, run_id, at)
    elif obs.target == IN_GROUP:
        representative = candidate_of_raw.get(obs.group_of_raw_item_id or -1)
        group_id = groups.get(representative) if representative else None
        if group_id is None and representative is not None:
            row = conn.execute(
                "SELECT group_id FROM candidate WHERE id = ?", (representative,)
            ).fetchone()
            group_id = row[0] if row else None
        if group_id is not None:
            _set_group(conn, candidate_id, group_id)
        count += transition(conn, candidate_id, GROUPED, IN_GROUP, obs.target_reason, run_id, at)
    return count


def _new_group(conn: Connection, label: str, at: datetime) -> int:
    cursor = conn.execute(
        "INSERT INTO candidate_group (label, created_at) VALUES (?, ?)", (label, to_utc_iso(at))
    )
    return int(cursor.lastrowid)


def _set_group(conn: Connection, candidate_id: int, group_id: int) -> None:
    conn.execute("UPDATE candidate SET group_id = ? WHERE id = ?", (group_id, candidate_id))


def _link_documents(
    conn: Connection, best: dict[int, Observation], candidate_of_raw: dict[int, int]
) -> None:
    """`representative_document_id`: o `source_document` da captura escolhida (DEC-064)."""
    for candidate_id, obs in best.items():
        conn.execute(
            "UPDATE candidate SET representative_document_id = ("
            "SELECT id FROM source_document WHERE raw_item_id = ?) "
            "WHERE id = ? AND representative_document_id IS NULL",
            (obs.raw_item_id, candidate_id),
        )


def _states(conn: Connection, ids: Collection[int]) -> dict[str, int]:
    counts: dict[str, int] = defaultdict(int)
    for chunk in _chunks(list(ids)):
        marks = ",".join("?" * len(chunk))
        for state, n in conn.execute(
            f"SELECT state, COUNT(*) FROM candidate WHERE id IN ({marks}) GROUP BY state", chunk
        ):
            counts[state] += int(n)
    return dict(sorted(counts.items()))


def _method_stats(
    conn: Connection, ids: Collection[int], new_discoveries: dict[str, int]
) -> dict[str, MethodStats]:
    methods_of: dict[int, set[str]] = defaultdict(set)
    for chunk in _chunks(list(ids)):
        marks = ",".join("?" * len(chunk))
        for candidate_id, method in conn.execute(
            f"SELECT candidate_id, method FROM candidate_discovery WHERE candidate_id IN ({marks})",
            chunk,
        ):
            methods_of[int(candidate_id)].add(method)
    stats: dict[str, MethodStats] = {}
    for method in sorted({m for ms in methods_of.values() for m in ms} | set(new_discoveries)):
        holders = [ms for ms in methods_of.values() if method in ms]
        stats[method] = MethodStats(
            candidates=len(holders),
            exclusive=sum(1 for ms in holders if ms == {method}),
            new_discoveries=new_discoveries.get(method, 0),
        )
    return stats


def _chunks(values: list[int], size: int = 500) -> list[list[int]]:
    return [values[i : i + size] for i in range(0, len(values), size)]


def candidate_transitions(path: Path, candidate_id: int) -> tuple[tuple[str | None, str, str], ...]:
    """Histórico (`from_state`, `to_state`, `reason`) de um candidato, por ordem."""
    conn = open_existing_database(Path(path))
    try:
        rows = conn.execute(
            "SELECT from_state, to_state, reason FROM candidate_transition "
            "WHERE candidate_id = ? ORDER BY id",
            (candidate_id,),
        ).fetchall()
    except sqlite3.Error as exc:
        raise StorageError(f"não foi possível ler transições: {exc}") from exc
    finally:
        conn.close()
    return tuple((row[0], row[1], row[2]) for row in rows)
