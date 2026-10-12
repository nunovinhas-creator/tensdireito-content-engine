"""Uma linha da tabela da §4.1 da especificação das fases 2–4 = um teste."""

import pytest

from tensdireito_content_engine.url_key import UrlKeyError, url_key


def test_scheme_and_host_are_lowercased():
    assert url_key("HTTPS://WWW.JN.pt/a") == "https://www.jn.pt/a"


def test_default_port_is_removed_and_other_ports_kept():
    assert url_key("https://eco.sapo.pt:443/x") == "https://eco.sapo.pt/x"
    assert url_key("https://eco.sapo.pt:8443/x") == "https://eco.sapo.pt:8443/x"


def test_fragment_is_removed():
    assert url_key("https://jn.pt/a#comentarios") == "https://jn.pt/a"


@pytest.mark.parametrize(
    "query",
    ["utm_source=x", "utm_medium=y&utm_campaign=z", "fbclid=1", "gclid=2", "ocid=3", "mc_cid=4"],
)
def test_tracking_parameters_are_removed(query):
    assert url_key(f"https://jn.pt/a?{query}") == "https://jn.pt/a"


def test_other_parameters_are_kept_and_sorted():
    assert url_key("https://jn.pt/a?b=2&a=1&utm_source=x") == "https://jn.pt/a?a=1&b=2"


def test_trailing_slash_is_removed_except_at_root():
    assert url_key("https://jn.pt/artigo/") == "https://jn.pt/artigo"
    assert url_key("https://jn.pt/") == "https://jn.pt/"
    assert url_key("https://jn.pt") == "https://jn.pt/"


@pytest.mark.parametrize(
    "url",
    [
        "https://jn.pt/artigo/amp/",
        "https://jn.pt/artigo/amp",
        "https://jn.pt/artigo?amp",
        "https://jn.pt/artigo?amp=1",
        "https://jn.pt/artigo?outputType=amp",
    ],
)
def test_amp_variants_collapse(url):
    assert url_key(url) == "https://jn.pt/artigo"


def test_www_joins_only_when_both_hosts_are_declared():
    assert url_key("https://www.jn.pt/a") == "https://www.jn.pt/a"
    assert url_key("https://www.jn.pt/a", {"jn.pt"}) == "https://www.jn.pt/a"
    assert url_key("https://www.jn.pt/a", {"jn.pt", "www.jn.pt"}) == "https://jn.pt/a"


def test_percent_encoding_is_uppercased_and_unreserved_decoded():
    assert url_key("https://jn.pt/a%c3%a7%7e") == "https://jn.pt/a%C3%A7~"


def test_same_article_variants_share_one_key():
    variants = (
        "https://JN.pt:443/artigo/?utm_source=bing#topo",
        "https://jn.pt/artigo/amp/",
        "https://jn.pt/artigo",
    )
    assert len({url_key(url) for url in variants}) == 1


@pytest.mark.parametrize("url", ["http://jn.pt/a", "ftp://jn.pt/a", "https:///a", "jn.pt/a"])
def test_non_https_or_hostless_urls_are_rejected(url):
    with pytest.raises(UrlKeyError):
        url_key(url)
