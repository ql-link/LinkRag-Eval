"""验证独立目标绑定和续接拒绝，不访问模型或真实 Qdrant。"""

from __future__ import annotations

import argparse
import asyncio
import fcntl
import json
import sqlite3
from pathlib import Path

import pytest

from linkrag_eval.config import EvalSettings
from linkrag_eval.runners import t2_workflow as workflow
from linkrag_eval.runners.t2_ingest import T2IngestError


def _encoding_summary(count=2):
    return {
        "total_rows": count, "completed_rows": count, "incomplete_rows": 0,
        "dense": {"shortened": 1, "unchanged": count - 1, "unknown": 0},
        "sparse": {"shortened": 0, "unchanged": count, "unknown": 0},
        "either_route_shortened": 1, "affected_status_unknown": 0,
    }


@pytest.fixture
def setup(tmp_path, monkeypatch):
    settings = EvalSettings(
        _env_file=None, embed_base_url="https://dense.invalid/v1", embed_api_key="dense-secret",
        sparse_api_key="sparse-secret", sparse_model="sparse-fixture", bm25_mode="sqlite_fts5",
        qdrant_host="http://qdrant.invalid:6333", user_id=990001,
    )
    collection = tmp_path / "collection.tsv"
    collection.write_text("pid\ttext\n0\t第一段\n1\t第二段\n", encoding="utf-8")
    calls = []

    async def ingest(**kwargs):
        calls.append(kwargs)
        result = {
            "processed_passages": 2, "indexed_passages": 2,
            "skipped_passages": 0, "completed_batches": 1,
            "encoding_inputs": _encoding_summary(),
        }
        kwargs["on_progress"](result)
        Path(kwargs["settings"].bm25_sqlite_path).touch()
        Path(kwargs["settings"].db_url.removeprefix("sqlite+aiosqlite:///")).touch()
        return result

    monkeypatch.setattr(workflow, "_run_ingestion", ingest)
    kwargs = {
        "collection_path": collection, "dataset_id": 991234, "doc_id_base": 8000000,
        "expected_passages": 2, "qdrant_prefix": "eval_t2_full", "out_dir": tmp_path / "corpus-run",
        "settings": settings,
    }
    return kwargs, calls


async def test_completed_run_is_rechecked_and_only_storage_settings_are_replaced(setup):
    kwargs, calls = setup
    result = await workflow.ingest_t2_corpus(**kwargs)
    assert result["status"] == "completed"
    metadata_path = kwargs["out_dir"] / "ingest.json"
    metadata = json.loads(metadata_path.read_text())
    assert "secret" not in metadata_path.read_text()
    metadata["code_revision"] = "previous-code-is-not-a-resume-restriction"
    metadata_path.write_text(json.dumps(metadata))
    await workflow.ingest_t2_corpus(**kwargs, batch_size=1)
    assert len(calls) == 2  # completed 进度也不能跳过实际 runner。
    original = kwargs["settings"].model_dump()
    effective = calls[-1]["settings"].model_dump()
    changed = {key for key in original if original[key] != effective[key]}
    assert changed == {"db_url", "bm25_sqlite_path", "qdrant_prefix"}
    assert calls[-1]["batch_size"] == 1
    assert metadata["source"]["collection_path"] == str(kwargs["collection_path"].resolve())


@pytest.mark.parametrize("change", [
    {"dataset_id": 991235}, {"doc_id_base": 8000001}, {"expected_passages": 3},
    {"qdrant_prefix": "eval_other"}, {"settings_update": {"embed_model": "other-model"}},
    {"settings_update": {"sparse_top_k": 32}},
    {"settings_update": {"embed_input_length_policy": "prefix_on_length_error"}},
    {"settings_update": {"sparse_input_length_policy": "prefix_on_length_error"}},
    {"settings_update": {"bm25_sqlite_fine_weight": 5.0}},
    {"settings_update": {"qdrant_host": "http://other.invalid:6333"}},
])
async def test_configuration_mismatch_rejects_before_storage_write(setup, change):
    kwargs, calls = setup
    await workflow.ingest_t2_corpus(**kwargs)
    previous = (kwargs["out_dir"] / "progress.json").read_bytes()
    updated = dict(kwargs)
    if "settings_update" in change:
        updated["settings"] = kwargs["settings"].model_copy(update=change["settings_update"])
    else:
        updated.update(change)
    with pytest.raises(ValueError, match="不匹配"):
        await workflow.ingest_t2_corpus(**updated)
    assert len(calls) == 1
    assert (kwargs["out_dir"] / "progress.json").read_bytes() == previous


async def test_source_path_and_unowned_directory_are_not_silently_adopted(setup, tmp_path):
    kwargs, calls = setup
    directory = kwargs["out_dir"]
    directory.mkdir()
    (directory / "unrelated.json").write_text("{}")
    with pytest.raises(ValueError, match="接管"):
        await workflow.ingest_t2_corpus(**kwargs)
    assert calls == []
    kwargs["out_dir"] = tmp_path / "fresh-run"
    await workflow.ingest_t2_corpus(**kwargs)
    copied_source = tmp_path / "different-collection.tsv"
    copied_source.write_bytes(kwargs["collection_path"].read_bytes())
    with pytest.raises(ValueError, match="不匹配"):
        await workflow.ingest_t2_corpus(**{**kwargs, "collection_path": copied_source})
    assert len(calls) == 1


async def test_concurrent_writer_rejected_before_runner(setup):
    kwargs, calls = setup
    kwargs["out_dir"].mkdir()
    with (kwargs["out_dir"] / ".ingest.lock").open("a") as stream:
        fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        with pytest.raises(ValueError, match="已有入库"):
            await workflow.ingest_t2_corpus(**kwargs)
    assert calls == []


async def test_incomplete_runner_return_never_becomes_completed(setup, monkeypatch):
    kwargs, _ = setup

    async def short_run(**_):
        return {
            "processed_passages": 1, "indexed_passages": 1,
            "skipped_passages": 0, "completed_batches": 1,
        }

    monkeypatch.setattr(workflow, "_run_ingestion", short_run)
    result = await workflow.ingest_t2_corpus(**kwargs)
    assert result["status"] == "failed"
    assert json.loads((kwargs["out_dir"] / "progress.json").read_text())["status"] == "failed"


async def test_completion_rejection_preserves_observed_encoding_summary(setup, monkeypatch):
    kwargs, _ = setup
    summary = _encoding_summary()
    summary["dense"]["unknown"] = 1

    async def unknown_length_run(**params):
        result = {
            "processed_passages": 2, "indexed_passages": 2,
            "skipped_passages": 0, "completed_batches": 1,
        }
        params["on_progress"](result)
        params["on_progress"]({"encoding_inputs": summary})
        return {**result, "encoding_inputs": summary}

    monkeypatch.setattr(workflow, "_run_ingestion", unknown_length_run)
    result = await workflow.ingest_t2_corpus(**kwargs)
    assert result["status"] == "failed"
    assert result["error_type"] == "ValueError"
    assert result["encoding_inputs"] == summary
    stored = json.loads((kwargs["out_dir"] / "progress.json").read_text())
    assert stored == result


@pytest.mark.parametrize("route", ["dense", "sparse"])
async def test_binding_rejects_completed_count_with_unknown_input_lengths(setup, route):
    kwargs, _ = setup
    await workflow.ingest_t2_corpus(**kwargs)
    progress_path = kwargs["out_dir"] / "progress.json"
    progress = json.loads(progress_path.read_text())
    progress["encoding_inputs"][route]["unknown"] = 1
    progress_path.write_text(json.dumps(progress))
    with pytest.raises(ValueError, match="实际编码输入长度"):
        workflow.bind_completed_t2_corpus(kwargs["out_dir"], kwargs["settings"])


async def test_batch_failure_only_records_safe_error_and_confirmed_progress(setup, monkeypatch):
    kwargs, _ = setup

    async def failed_run(**params):
        params["on_progress"]({"encoding_inputs": {"completed_rows": 1, "incomplete_rows": 1}})
        raise T2IngestError(
            phase="index", progress={
                "processed_passages": 1, "indexed_passages": 1,
                "skipped_passages": 0, "completed_batches": 1,
            }, first_position=1, batch_count=1, error_type="DenseEncodeError",
            cause_chain=[{"error_type": "UnexpectedResponse", "http_status": 429}],
        ) from ValueError("REMOTE API KEY secret and full text")

    monkeypatch.setattr(workflow, "_run_ingestion", failed_run)
    result = await workflow.ingest_t2_corpus(**kwargs)
    assert result["processed_passages"] == 1
    assert result["failed_batch"] == {"first_position": 1, "passage_count": 1}
    assert result["phase"] == "index"
    assert result["encoding_inputs"] == {"completed_rows": 1, "incomplete_rows": 1}
    assert result["cause_chain"] == [{"error_type": "UnexpectedResponse", "http_status": 429}]
    assert json.loads((kwargs["out_dir"] / "progress.json").read_text())["cause_chain"] == result["cause_chain"]
    assert "secret" not in (kwargs["out_dir"] / "progress.json").read_text()


async def test_task_cancellation_preserves_confirmed_progress_and_releases_lock(setup, monkeypatch):
    kwargs, _ = setup
    confirmed = asyncio.Event()
    partial = {
        "processed_passages": 1, "indexed_passages": 1,
        "skipped_passages": 0, "completed_batches": 1,
    }

    async def waiting_run(**params):
        params["on_progress"](partial)
        confirmed.set()
        await asyncio.Event().wait()

    monkeypatch.setattr(workflow, "_run_ingestion", waiting_run)
    task = asyncio.create_task(workflow.ingest_t2_corpus(**kwargs))
    await asyncio.wait_for(confirmed.wait(), timeout=1)
    task.cancel("secret cancellation detail")
    with pytest.raises(asyncio.CancelledError):
        await task
    progress_path = kwargs["out_dir"] / "progress.json"
    result = json.loads(progress_path.read_text())
    assert result["status"] == "interrupted"
    assert result["error_type"] == "CancelledError"
    assert {key: result[key] for key in partial} == partial
    assert "secret" not in progress_path.read_text()
    with workflow._run_lock(kwargs["out_dir"]):
        pass


async def test_keyboard_interrupt_is_recorded_and_reraised(setup, monkeypatch):
    kwargs, _ = setup

    async def interrupted_run(**params):
        params["on_progress"]({
            "processed_passages": 1, "indexed_passages": 0,
            "skipped_passages": 1, "completed_batches": 1,
        })
        raise KeyboardInterrupt

    monkeypatch.setattr(workflow, "_run_ingestion", interrupted_run)
    with pytest.raises(KeyboardInterrupt):
        await workflow.ingest_t2_corpus(**kwargs)
    result = json.loads((kwargs["out_dir"] / "progress.json").read_text())
    assert result["status"] == "interrupted"
    assert result["error_type"] == "KeyboardInterrupt"
    assert result["processed_passages"] == result["skipped_passages"] == 1
    with workflow._run_lock(kwargs["out_dir"]):
        pass


async def test_binding_requires_completed_matching_encoders_and_local_stores(setup):
    kwargs, _ = setup
    await workflow.ingest_t2_corpus(**kwargs)
    effective, collection, dataset_id = workflow.bind_completed_t2_corpus(
        kwargs["out_dir"], kwargs["settings"],
    )
    assert collection == kwargs["collection_path"]
    assert dataset_id == kwargs["dataset_id"]
    assert effective.qdrant_prefix == "eval_t2_full"
    assert effective.db_url.endswith("corpus-run/corpus.sqlite3")
    wrong = kwargs["settings"].model_copy(update={"embed_dim": 128})
    with pytest.raises(ValueError, match="不匹配"):
        workflow.bind_completed_t2_corpus(kwargs["out_dir"], wrong)
    progress_path = kwargs["out_dir"] / "progress.json"
    progress = json.loads(progress_path.read_text())
    progress["status"] = "failed"
    progress_path.write_text(json.dumps(progress))
    with pytest.raises(ValueError, match="尚未完成"):
        workflow.bind_completed_t2_corpus(kwargs["out_dir"], kwargs["settings"])


def test_endpoint_credentials_and_query_are_not_persisted():
    assert workflow._endpoint("https://user:password@example.com/v1?api_key=secret#token") == (
        "https://example.com/v1"
    )


def _parser():
    from linkrag_eval.cli import _add_exploration

    parser = argparse.ArgumentParser()
    _add_exploration(parser.add_subparsers(dest="command"))
    return parser


def test_cli_corpus_run_and_manual_dataset_are_mutually_exclusive():
    argv = [
        "exploration", "candidates", "--queries", "queries.tsv", "--sample-size", "2",
        "--seed", "1", "--out-dir", "candidate-run", "--corpus-run", "corpus-run",
    ]
    parsed = _parser().parse_args(argv)
    assert parsed.dataset_id is None
    assert parsed.collection is None
    with pytest.raises(SystemExit) as error:
        _parser().parse_args([*argv, "--dataset-id", "123"])
    assert error.value.code == 2


async def test_cli_binds_completed_corpus_before_collecting(setup, monkeypatch):
    from linkrag_eval import cli, config
    from linkrag_eval.runners import exploration_workflow

    kwargs, _ = setup
    await workflow.ingest_t2_corpus(**kwargs)
    monkeypatch.setattr(config, "get_settings", lambda: kwargs["settings"])
    called = []

    async def collect(**params):
        called.append(params)
        return {"input_status_counts": {"ready": 2}}

    monkeypatch.setattr(exploration_workflow, "prepare_exploration_candidates", collect)
    args = _parser().parse_args([
        "exploration", "candidates", "--queries", "queries.tsv", "--sample-size", "2",
        "--seed", "1", "--out-dir", "candidate-run", "--corpus-run", str(kwargs["out_dir"]),
    ])
    assert await cli._do_exploration(args) == 0
    assert called[0]["corpus_run"] == kwargs["out_dir"]
    assert called[0]["settings"].qdrant_prefix == "eval_t2_full"
    assert called[0]["dataset_id"] == kwargs["dataset_id"]
    assert called[0]["collection_path"] == kwargs["collection_path"]
    args.collection = "manual.tsv"
    with pytest.raises(ValueError, match="不能同时"):
        await cli._do_exploration(args)
    assert len(called) == 1


@pytest.mark.parametrize("fail_runner", [False, True, "cancelled", "close_failed", "summary_failed"])
async def test_real_assembly_uses_explicit_settings_and_closes_clients(
    tmp_path, monkeypatch, fail_runner,
):
    from linkrag_eval.llm import dense_client, sparse_client
    from linkrag_eval.store import corpus_repo, sqlite_bm25, vector_store

    settings = EvalSettings(
        _env_file=None, bm25_mode="sqlite_fts5", sparse_model="test-sparse",
        db_url=f"sqlite+aiosqlite:///{tmp_path / 'corpus.sqlite3'}",
        bm25_sqlite_path=str(tmp_path / "bm25.sqlite3"),
    )
    events = []
    observed_progress = []
    summary_failure = ValueError("summary failed")

    class Encoder:
        dim = settings.embed_dim

        def __init__(self, name):
            self.name = name

        async def aclose(self):
            events.append(f"close-{self.name}")
            if fail_runner == "close_failed" and self.name == "dense":
                raise RuntimeError("close failed")

    def dense_builder(actual):
        assert actual is settings
        return Encoder("dense")

    def sparse_builder(actual):
        assert actual is settings
        return Encoder("sparse")

    class Repo:
        def __init__(self, *, url):
            assert url == settings.db_url

        async def register_dataset(self, dataset_id, **_):
            events.append("register")
            assert dataset_id == 123

        async def summarize_encoding_inputs(self, *, dataset_id):
            events.append("summarize")
            assert dataset_id == 123
            if fail_runner == "summary_failed":
                raise summary_failure
            return _encoding_summary()

    class BM25:
        def __init__(self, path, **_):
            assert path == settings.bm25_sqlite_path

        async def ensure_collection(self):
            events.append("bm25")

    class Vectors:
        def __init__(self, **params):
            assert isinstance(params["bm25_store"], BM25)
            assert params["prefix"] == settings.qdrant_prefix

        async def prepare_collection(self, **params):
            assert params == {"vector_size": settings.embed_dim, "dataset_id": 123, "on_disk": True}
            events.append("vectors")

        async def aclose(self):
            events.append("close-vectors")

    def migrate(url):
        assert url == settings.db_url
        events.append("migrate")

    async def ingest(**params):
        events.append("ingest")
        assert params["expected_passage_count"] == 2
        if fail_runner == "cancelled":
            raise asyncio.CancelledError
        if fail_runner is True:
            raise RuntimeError("runner failed")
        return {"processed_passages": 2}

    monkeypatch.setattr(dense_client, "build_dense_embedder", dense_builder)
    monkeypatch.setattr(sparse_client, "build_sparse_encoder", sparse_builder)
    monkeypatch.setattr(corpus_repo, "EvalCorpusRepo", Repo)
    monkeypatch.setattr(sqlite_bm25, "SQLiteBm25Store", BM25)
    monkeypatch.setattr(vector_store, "EvalVectorStore", Vectors)
    monkeypatch.setattr(workflow, "migrate_corpus_database", migrate)
    monkeypatch.setattr(workflow, "ingest_t2_collection", ingest)
    operation = workflow._run_ingestion(
        settings=settings, collection_path=tmp_path / "collection.tsv", dataset_id=123,
        doc_id_base=1000, batch_size=25, expected_passages=2,
        on_progress=observed_progress.append,
    )
    if fail_runner == "cancelled":
        with pytest.raises(asyncio.CancelledError):
            await operation
    elif fail_runner is True:
        with pytest.raises(RuntimeError, match="runner failed"):
            await operation
    elif fail_runner == "close_failed":
        with pytest.raises(RuntimeError, match="close failed"):
            await operation
    elif fail_runner == "summary_failed":
        with pytest.raises(ValueError, match="summary failed") as error:
            await operation
        assert error.value is summary_failure
    else:
        assert await operation == {"processed_passages": 2, "encoding_inputs": _encoding_summary()}
    assert events == [
        "migrate", "vectors", "bm25", "register", "ingest", "summarize",
        "close-vectors", "close-sparse", "close-dense",
    ]
    expected_summary = (
        {"status": "unavailable", "error_type": "ValueError"}
        if fail_runner == "summary_failed" else _encoding_summary()
    )
    assert observed_progress == [{"encoding_inputs": expected_summary}]


def test_programmatic_migration_uses_explicit_database_and_runs_from_empty(tmp_path, monkeypatch):
    intended = tmp_path / "corpus.sqlite3"
    forbidden = tmp_path / "default.sqlite3"
    monkeypatch.setenv("ALEMBIC_DATABASE_URL", f"sqlite:///{forbidden}")
    monkeypatch.setenv("EVAL_DB_URL", f"sqlite+aiosqlite:///{forbidden}")
    workflow.migrate_corpus_database(f"sqlite+aiosqlite:///{intended}")
    assert not forbidden.exists()
    with sqlite3.connect(intended) as connection:
        assert connection.execute("SELECT version_num FROM alembic_version").fetchone() == ("0004",)
        columns = {row[1] for row in connection.execute("PRAGMA table_info(eval_run)")}
        assert {"run_quality", "failed_samples", "failed_sources_json", "zero_ranked"} <= columns
    workflow.migrate_corpus_database(f"sqlite+aiosqlite:///{intended}")


@pytest.mark.parametrize("existing_type", [None, "TEXT"])
def test_quality_migration_adds_missing_fields_but_rejects_incompatible_existing(
    tmp_path, existing_type,
):
    target = tmp_path / "corpus.sqlite3"
    with sqlite3.connect(target) as connection:
        definition = "id INTEGER PRIMARY KEY"
        if existing_type:
            definition += f", run_quality {existing_type}"
        connection.execute(f"CREATE TABLE eval_run ({definition})")
        connection.execute("CREATE TABLE eval_corpus_chunk (chunk_id TEXT PRIMARY KEY)")
        connection.execute("INSERT INTO eval_run(id) VALUES (7)")
        connection.execute("CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL)")
        connection.execute("INSERT INTO alembic_version VALUES ('0002')")
    if existing_type:
        with pytest.raises(ValueError, match="类型或可空性不一致"):
            workflow.migrate_corpus_database(f"sqlite+aiosqlite:///{target}")
    else:
        workflow.migrate_corpus_database(f"sqlite+aiosqlite:///{target}")
    with sqlite3.connect(target) as connection:
        assert connection.execute("SELECT id FROM eval_run").fetchone() == (7,)
