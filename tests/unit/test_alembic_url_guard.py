"""Migration URL selection and isolation, with no real settings or connections."""

from __future__ import annotations

import runpy
from contextlib import nullcontext
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
import sqlalchemy
from alembic.config import Config

from alembic import context
from linkrag_eval import config as settings_module

ENVIRONMENT = Path(__file__).resolve().parents[2] / "alembic" / "env.py"


@pytest.fixture
def migration(monkeypatch):
    monkeypatch.delenv("ALEMBIC_DATABASE_URL", raising=False)
    configuration = Config()
    configuration.set_main_option("sqlalchemy.url", "mysql+pymysql://example.invalid/unused")
    settings = Mock(return_value=SimpleNamespace(database_url=lambda: "sqlite+aiosqlite:///default.db"))
    monkeypatch.setattr(settings_module, "get_settings", settings)
    configure, migrate = Mock(), Mock()
    engine = Mock()
    engine.return_value.connect.return_value = nullcontext(object())
    monkeypatch.setattr(sqlalchemy, "engine_from_config", engine)
    monkeypatch.setattr(context, "config", configuration, raising=False)
    monkeypatch.setattr(context, "configure", configure)
    monkeypatch.setattr(context, "run_migrations", migrate)
    monkeypatch.setattr(context, "begin_transaction", lambda: nullcontext())

    def select(source, url):
        if source == "explicit":
            configuration.attributes["database_url"] = url
        elif source == "environment":
            monkeypatch.setenv("ALEMBIC_DATABASE_URL", url)
        else:
            settings.return_value = SimpleNamespace(database_url=lambda: url)

    def execute(offline):
        monkeypatch.setattr(context, "is_offline_mode", lambda: offline)
        return runpy.run_path(str(ENVIRONMENT))

    return SimpleNamespace(
        config=configuration, settings=settings, configure=configure,
        migrate=migrate, engine=engine, select=select, execute=execute,
    )


@pytest.mark.parametrize("offline", [False, True])
@pytest.mark.parametrize("source", ["explicit", "environment", "settings"])
@pytest.mark.parametrize("url", [
    "mysql+pymysql://example.invalid/forbidden",
    "postgresql://example.invalid/forbidden",
    "sqlite://example.invalid/forbidden",
    "",
])
def test_nonlocal_or_empty_url_stops_before_engine_or_migration(migration, offline, source, url):
    migration.select(source, url)
    with pytest.raises(ValueError, match="SQLite"):
        migration.execute(offline)
    migration.engine.assert_not_called()
    migration.configure.assert_not_called()
    migration.migrate.assert_not_called()


@pytest.mark.parametrize("offline", [False, True])
@pytest.mark.parametrize("source", ["explicit", "environment", "settings"])
@pytest.mark.parametrize("driver", ["sqlite", "sqlite+aiosqlite"])
def test_all_sources_normalize_local_sqlite_for_both_migration_modes(
    migration, tmp_path, offline, source, driver,
):
    database = tmp_path / "corpus.db"
    migration.select(source, f"{driver}:///{database}")
    migration.execute(offline)
    expected = f"sqlite:///{database}"
    assert migration.config.get_main_option("sqlalchemy.url") == expected
    if offline:
        migration.engine.assert_not_called()
        assert migration.configure.call_args.kwargs["url"] == expected
    else:
        assert migration.engine.call_args.args[0]["sqlalchemy.url"] == expected
    migration.migrate.assert_called_once_with()
    assert not database.exists()


@pytest.mark.parametrize("offline", [False, True])
def test_settings_errors_cannot_fall_back_to_ini_url(migration, offline):
    error = RuntimeError("synthetic invalid EVAL_DB_URL")
    migration.settings.side_effect = error
    with pytest.raises(RuntimeError, match="synthetic invalid") as raised:
        migration.execute(offline)
    assert raised.value is error
    migration.engine.assert_not_called()
    migration.configure.assert_not_called()


def test_explicit_sqlite_has_priority_over_environment_and_settings(migration):
    migration.select("environment", "postgresql://example.invalid/unused")
    migration.select("explicit", "sqlite+aiosqlite:///:memory:")
    migration.settings.side_effect = AssertionError("lower-priority settings must not be read")
    migration.execute(True)
    assert migration.configure.call_args.kwargs["url"] == "sqlite:///:memory:"
    migration.settings.assert_not_called()


def test_environment_sqlite_has_priority_over_settings(migration):
    migration.select("environment", "sqlite:///relative.db")
    migration.settings.side_effect = AssertionError("lower-priority settings must not be read")
    migration.execute(True)
    assert migration.configure.call_args.kwargs["url"] == "sqlite:///relative.db"
    migration.settings.assert_not_called()


def test_default_settings_override_ini_instead_of_using_it_as_another_source(migration):
    migration.execute(True)
    assert migration.configure.call_args.kwargs["url"] == "sqlite:///default.db"
    migration.settings.assert_called_once_with()
