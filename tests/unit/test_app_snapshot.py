"""检索运行快照必须足以证明 BM25 backend 与计算口径。"""

from __future__ import annotations

import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from linkrag_eval import app
from linkrag_eval.compute.protocol import Bm25Tokens
from linkrag_eval.store.sqlite_bm25 import SQLiteBm25Point, SQLiteBm25Store


async def test_minimal_snapshot_captures_sqlite_identity_and_fingerprint(
    tmp_path, monkeypatch
) -> None:
    sidecar = tmp_path / "bm25.sqlite3"
    store = SQLiteBm25Store(sidecar)
    await store.upsert_chunks(
        [
            SQLiteBm25Point(
                chunk_id="c1",
                doc_id=1,
                user_id=990001,
                dataset_id=992000,
                chunk_type="text",
                tokens=Bm25Tokens(coarse="验 收", fine="验 收"),
            )
        ]
    )
    monkeypatch.setattr(app, "_git_state", lambda: ("abc123", True))
    settings = SimpleNamespace(
        sparse_provider="ark",
        sparse_model="sparse-v1",
        embed_model="dense-v1",
        embed_dim=1024,
        recall_dense_score_threshold=0.3,
        recall_sparse_score_threshold=0.1,
        recall_dense_top_k=150,
        recall_sparse_top_k=50,
        recall_bm25_top_k=100,
        recall_dense_weight=0.70,
        recall_sparse_weight=0.15,
        recall_bm25_weight=0.15,
        bm25_mode="sqlite_fts5",
        bm25_sqlite_path=str(sidecar),
        bm25_sqlite_coarse_weight=2.0,
        bm25_sqlite_fine_weight=1.0,
    )

    snapshot = app._minimal_snapshot("r1", 10, settings=settings)

    assert snapshot.git_sha == "abc123"
    assert snapshot.git_dirty is True
    assert snapshot.route_score_thresholds == {"dense": 0.3, "sparse": 0.1}
    assert snapshot.bm25_mode == "sqlite_fts5"
    assert snapshot.bm25_sidecar_identity["chunk_count"] == 1
    assert snapshot.bm25_sidecar_identity["dataset_counts"] == {"992000": 1}
    assert snapshot.computer_fingerprint["dense"] == {"model": "dense-v1", "dim": 1024}
    assert snapshot.computer_fingerprint["sparse"]["model"] == "sparse-v1"
    assert snapshot.feature_version == "recall_pipeline_v1"


@pytest.mark.parametrize("status", [b"", b"A  staged.py\0", b"?? untracked.py\0"])
def test_git_state_uses_status_without_opening_worktree_files(monkeypatch, status) -> None:
    def run(command, **kwargs):
        if command == ["git", "rev-parse", "HEAD"]:
            return SimpleNamespace(stdout="abc123\n")
        assert command == ["git", "status", "--porcelain", "-z"]
        return SimpleNamespace(stdout=status)

    def reject_read(path):
        raise AssertionError(f"snapshot must not read worktree file contents: {path}")

    monkeypatch.setattr(app.subprocess, "run", run)
    monkeypatch.setattr(Path, "read_bytes", reject_read)
    assert app._git_state() == ("abc123", bool(status))


def test_git_state_reports_unknown_on_git_failure(monkeypatch) -> None:
    def run(command, **kwargs):
        raise subprocess.CalledProcessError(1, command)

    monkeypatch.setattr(app.subprocess, "run", run)
    assert app._git_state() == ("unknown", True)


def test_snapshot_rejects_removed_bm25_backend(monkeypatch) -> None:
    monkeypatch.setattr(app, "_git_state", lambda: ("abc123", False))
    with pytest.raises(ValueError, match="不支持的 BM25 模式"):
        app._minimal_snapshot("r1", 10, settings=SimpleNamespace(bm25_mode="qdrant_bm25"))
