"""普通 run 的历史保全：真实文件/临时 SQLite，召回使用 fake。"""

from __future__ import annotations

import argparse
import asyncio
import json
from types import SimpleNamespace

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from linkrag_eval import cli
from linkrag_eval.config import EvalSettings
from linkrag_eval.metrics.retrieval import RecallAtK
from linkrag_eval.models import Layer, RankedHit, StageOutput
from linkrag_eval.store.db_result_store import EvalDbResultStore
from linkrag_eval.store.filesystem import FilesystemResultStore
from linkrag_eval.store.models import EvalBase, EvalMetricResultDB, EvalRunDB


@pytest.fixture
async def harness(tmp_path, monkeypatch):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'test.sqlite3'}")
    async with engine.begin() as connection:
        await connection.run_sync(EvalBase.metadata.create_all)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    db = EvalDbResultStore(sessions)
    state = SimpleNamespace(calls=0, builds=0, hit=True, error=None, entered=None, release=None)

    class FakeRecall:
        layer = Layer.RETRIEVAL

        async def run(self, sample, *, upstream=None):
            state.calls += 1
            if state.entered is not None:
                state.entered.set()
                await state.release.wait()
            if state.error is not None:
                raise state.error
            return StageOutput(
                layer=self.layer,
                query=sample.query,
                ranked=[RankedHit("c1", 1 if state.hit else 2, 990131, 0, 0.9)],
            )

    def build(*args, **kwargs):
        state.builds += 1
        return FakeRecall()

    from linkrag_eval import config, metrics, retrieval
    from linkrag_eval.store import db_result_store

    monkeypatch.setattr(config, "get_settings", lambda: EvalSettings(_env_file=None))
    monkeypatch.setattr(retrieval, "build_eval_recall_evaluable", build)
    monkeypatch.setattr(metrics.retrieval, "default_retrieval_metrics", lambda: [RecallAtK([10])])
    monkeypatch.setattr(db_result_store, "EvalDbResultStore", lambda: db)
    golden = tmp_path / "golden.jsonl"
    golden.write_text(json.dumps({
        "id": "q1", "query": "synthetic", "user_id": 1,
        "dataset_ids": [990131], "expected_doc_ids": [1],
    }), encoding="utf-8")
    parser = argparse.ArgumentParser()
    cli._add_run(parser.add_subparsers())

    def args(*extra):
        return parser.parse_args([
            "run", "--golden", str(golden), "--out-dir", str(tmp_path / "out"), *extra,
        ])

    try:
        yield SimpleNamespace(
            db=db, sessions=sessions, state=state, args=args, root=tmp_path,
        )
    finally:
        await engine.dispose()


def _files(root):
    return {str(p.relative_to(root)): p.read_bytes() for p in root.rglob("*") if p.is_file()}


async def test_repeated_run_preserves_files_and_database(harness):
    h = harness
    assert await cli._do_run(h.args()) == 0
    before = _files(h.root / "out")
    h.state.hit = False
    with pytest.raises(FileExistsError, match="run-top10"):
        await cli._do_run(h.args())
    assert h.state.calls == h.state.builds == 1
    assert _files(h.root / "out") == before
    baseline = await h.db.load_baseline("run-top10")
    assert baseline.metrics[0].mean == 1.0


@pytest.mark.parametrize("artifact", [
    "snapshots/run-top10.json", "results/run-top10.json", "reports/run-top10.html",
    "run-top10.html", "run-top10.json",
])
async def test_existing_partial_output_rejected_before_recall_and_db_write(harness, artifact):
    h = harness
    out = h.root / "out"
    path = out / artifact
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"historical partial artifact")
    with pytest.raises(FileExistsError, match="run-top10"):
        await cli._do_run(h.args())
    assert path.read_bytes() == b"historical partial artifact"
    assert h.state.calls == h.state.builds == 0
    async with h.sessions() as session:
        assert await session.get(EvalRunDB, "run-top10") is None


async def test_dangling_output_link_is_an_existing_artifact(harness):
    h = harness
    out = h.root / "out"
    out.mkdir()
    path = out / "run-top10.json"
    target = out / "missing.json"
    path.symlink_to(target)
    with pytest.raises(FileExistsError, match="run-top10"):
        await cli._do_run(h.args())
    assert path.is_symlink() and not target.exists()
    assert h.state.builds == 0


async def test_shared_db_collision_across_directory_and_dataset(harness):
    h = harness
    assert await cli._do_run(h.args()) == 0
    before = _files(h.root / "out")
    other = h.root / "other"
    h.state.hit = False
    with pytest.raises(FileExistsError, match="run-top10"):
        await cli._do_run(h.args("--out-dir", str(other), "--dataset", "other"))
    assert h.state.calls == h.state.builds == 1
    assert _files(h.root / "out") == before
    assert _files(other) == {}
    baseline = await h.db.load_baseline("run-top10")
    assert baseline.metrics[0].mean == 1.0
    async with h.sessions() as session:
        runs = (await session.scalars(select(EvalRunDB))).all()
        assert len(runs) == 1
        assert json.loads(runs[0].dataset_ids_json) == {"dataset": "default"}


@pytest.mark.parametrize("status", ["failed", "running", "done", None])
async def test_database_only_partial_run_blocks_new_output(harness, status):
    h = harness
    async with h.sessions() as session:
        if status is not None:
            session.add(EvalRunDB(run_id="run-top10", status=status))
        session.add(EvalMetricResultDB(
            run_id="run-top10", layer="retrieval", metric="recall_doc", k=10,
            relevance_scale="binary", type_bucket="__all__", value=1.0, n=1, n_samples=1,
        ))
        await session.commit()
    with pytest.raises(FileExistsError, match="run-top10"):
        await cli._do_run(h.args())
    assert h.state.builds == 0
    assert _files(h.root / "out") == {}
    async with h.sessions() as session:
        run = await session.get(EvalRunDB, "run-top10")
        assert (run.status if run else None) == status
        assert (await session.scalar(select(EvalMetricResultDB.value))) == 1.0


async def test_distinct_run_compares_saved_baseline(harness):
    h = harness
    assert await cli._do_run(h.args("--run-label", "old")) == 0
    before = _files(h.root / "out")
    h.state.hit = False
    assert await cli._do_run(h.args("--run-label", "new", "--baseline", "old-top10")) == 0
    after = _files(h.root / "out")
    assert all(after[path] == content for path, content in before.items())
    report = json.loads(after["new-top10.json"])
    assert report["baseline_run_id"] == "old-top10"
    assert report["deltas"][0]["value"] == 0.0
    assert report["deltas"][0]["baseline_value"] == 1.0
    baseline = FilesystemResultStore(h.root / "out").load_baseline("old-top10")
    assert baseline.metrics[0].mean == 1.0
    async with h.sessions() as session:
        run = await session.get(EvalRunDB, "new-top10")
        assert run.status == "done" and run.baseline_run_id == "old-top10"


@pytest.mark.parametrize("baseline", ["run-top10", "missing-top10"])
async def test_invalid_baseline_rejected_before_any_run_write(harness, baseline):
    h = harness
    with pytest.raises(ValueError, match="基线"):
        await cli._do_run(h.args("--baseline", baseline))
    assert h.state.builds == 0
    assert _files(h.root / "out") == {}
    async with h.sessions() as session:
        assert (await session.scalars(select(EvalRunDB))).all() == []


@pytest.mark.parametrize("label", ["../escape", "nested/run", "nested\\run", "x" * 96])
async def test_run_label_cannot_escape_filename_or_exceed_id_width(harness, label):
    with pytest.raises(ValueError, match="run_id"):
        await cli._do_run(harness.args("--run-label", label))
    assert harness.state.builds == 0


@pytest.mark.parametrize("same_directory", [False, True])
async def test_concurrent_same_id_only_one_reaches_recall(harness, same_directory):
    h = harness
    h.state.entered, h.state.release = asyncio.Event(), asyncio.Event()
    first = asyncio.create_task(cli._do_run(h.args()))
    try:
        await asyncio.wait_for(h.state.entered.wait(), timeout=5)
        other = h.root / ("out" if same_directory else "other")
        with pytest.raises(FileExistsError, match="run-top10"):
            await cli._do_run(h.args("--out-dir", str(other)))
        assert h.state.calls == h.state.builds == 1
        # 失败的一方不能释放首个运行的锁或将其台账标为 failed。
        assert (h.root / "out" / ".run-run-top10.lock").exists()
        async with h.sessions() as session:
            assert (await session.get(EvalRunDB, "run-top10")).status == "running"
    finally:
        h.state.release.set()
        await first
    assert not (h.root / "out" / ".run-run-top10.lock").exists()
    assert (await h.db.load_baseline("run-top10")).metrics[0].mean == 1.0


async def test_different_ids_run_concurrently_without_holding_db_transaction(harness):
    h = harness
    h.state.entered, h.state.release = asyncio.Event(), asyncio.Event()
    first = asyncio.create_task(cli._do_run(h.args("--run-label", "first")))
    await asyncio.wait_for(h.state.entered.wait(), timeout=5)
    h.state.entered.clear()
    second = asyncio.create_task(cli._do_run(h.args("--run-label", "second")))
    try:
        await asyncio.wait_for(h.state.entered.wait(), timeout=5)
        assert h.state.calls == 2
    finally:
        h.state.release.set()
        assert await asyncio.gather(first, second) == [0, 0]
    async with h.sessions() as session:
        assert (await session.scalars(select(EvalRunDB.status))).all() == ["done", "done"]


@pytest.mark.parametrize("cancelled", [False, True])
async def test_failure_preserves_partial_output_and_marks_claim_failed(harness, monkeypatch, cancelled):
    from linkrag_eval import app

    h = harness
    snapshot = h.root / "out" / "snapshots" / "run-top10.json"
    error = asyncio.CancelledError() if cancelled else RuntimeError("synthetic failure")

    async def fail(*args, **kwargs):
        snapshot.write_bytes(b"partial evidence")
        raise error

    monkeypatch.setattr(app, "run_eval", fail)
    with pytest.raises(type(error)):
        await cli._do_run(h.args())
    assert snapshot.read_bytes() == b"partial evidence"
    assert not (h.root / "out" / ".run-run-top10.lock").exists()
    async with h.sessions() as session:
        run = await session.get(EvalRunDB, "run-top10")
        assert run.status == "failed" and run.finished_at is not None
    with pytest.raises(FileExistsError, match="run-top10"):
        await cli._do_run(h.args("--out-dir", str(h.root / "retry")))


async def test_mismatched_baseline_identity_rejected_before_claim(harness):
    h = harness
    assert await cli._do_run(h.args("--run-label", "old")) == 0
    baseline = h.root / "out" / "results" / "old-top10.json"
    payload = json.loads(baseline.read_text())
    payload["run_id"] = "wrong-id"
    baseline.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="基线"):
        await cli._do_run(h.args("--baseline", "old-top10"))
    assert h.state.builds == 1
    async with h.sessions() as session:
        assert await session.get(EvalRunDB, "run-top10") is None
