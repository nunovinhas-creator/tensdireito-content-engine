import dataclasses
from pathlib import Path

import pytest

from tensdireito_content_engine import __version__
from tensdireito_content_engine.config import (
    APP_NAME,
    AppConfig,
    Environment,
    load_config,
    sources_path,
)


def test_default_config_is_safe_and_reuses_package_version():
    config = load_config()
    assert config.app_name == APP_NAME
    assert config.version == __version__
    assert config.environment is Environment.DEVELOPMENT


def test_config_for_tests():
    assert load_config(Environment.TEST).environment is Environment.TEST


def test_config_is_deterministic_and_immutable():
    config = load_config()
    assert config == load_config()
    with pytest.raises(dataclasses.FrozenInstanceError):
        config.environment = Environment.TEST  # type: ignore[misc]


def test_config_rejects_unknown_environment():
    with pytest.raises(ValueError):
        AppConfig(environment="production")  # type: ignore[arg-type]


def test_config_rejects_empty_name():
    with pytest.raises(ValueError):
        AppConfig(app_name=" ")


def test_sources_path_defaults_to_config_dir():
    assert sources_path() == Path("config/sources.yaml")
    assert sources_path(Path("outra")) == Path("outra/sources.yaml")
