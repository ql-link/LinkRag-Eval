"""Offline checks for bounded requests, resumable candidate tails and honest coverage."""
from __future__ import annotations

import importlib.util
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest

spec = importlib.util.spec_from_file_location(
    "nevir_ltr_collect_script", Path(__file__).resolve().parents[2] / "scripts/nevir_ltr_collect.py")
collector = importlib.util.module_from_spec(spec)
spec.loader.exec_module(collector)


class Encoder:
    def __init__(self, client):
        self.client = client

    async def _get_client(self):
        return self.client


def supervision(qid="q0", *, conflict=False, uncertain=False):
    return {"source_query_id": qid, "role": "train", "source_group_id": "g0", "pair_id": "pair0",
            "direction": "q1", "official_label_available": True, "structural_conflict": conflict,
            "semantic_uncertain": uncertain, "preferred_chunk_id": "c1", "other_chunk_id": "c2",
            "preferred_passage_id": "p1", "other_passage_id": "p2"}


def candidate(qid="q0", *, status="ready", ids=("c1", "c2")):
    hits = [{"dataset_id": 995300, "doc_id": i, "chunk_id": cid, "score": .8, "rank": i}
            for i, cid in enumerate(ids)]
    return {"source_query_id": qid, "query": "query " + qid, "routes": {
        "dense": hits, "sparse": [], "bm25": hits},
        "candidate_rows": [{"chunk_id": cid, "source_passage_id": "p" + cid[1:],
                            "content": "body " + cid} for cid in ids],
        "status": status, "ranking_input_ready": status in {"ready", "empty"},
        "route_status": {"dense": "ok" if ids else "empty", "sparse": "empty",
                         "bm25": "ok" if ids else "empty"},
        "failed_sources": ["dense"] if status == "failed" else []}


def prepare(tmp_path, count=3):
    p = tmp_path / "prepared/train"
    p.mkdir(parents=True)
    (tmp_path / "candidates/train").mkdir(parents=True)
    collector.write_rows(p / "queries.jsonl", [{"source_query_id": f"q{i}", "query": f"query q{i}"}
                                                for i in range(count)])
    collector.write_rows(p / "supervision.jsonl", [supervision(f"q{i}") for i in range(count)])


async def test_budget_is_global_across_routes_and_persists_across_resume(tmp_path):
    reached = []

    def handle(request):
        reached.append(request)
        return httpx.Response(200, json={})

    path = tmp_path / "requests.jsonl"
    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
        budget = collector.RequestBudget(path, stage="train", limit=2)
        await budget.instrument(Encoder(client), "dense")
        await client.post("https://encoder.invalid")
        budget.close()
    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
        resumed = collector.RequestBudget(path, stage="train", limit=2)
        await resumed.instrument(Encoder(client), "sparse")
        await client.post("https://encoder.invalid")
        with pytest.raises(collector.RequestLimitExceeded):
            await client.post("https://encoder.invalid")
        assert resumed.summary()["encoder_request_counts"] == {"dense": 1, "sparse": 1}
        resumed.close()
    assert len(reached) == 2
    assert sum(x["event"] == "request" for x in collector.rows(path)) == 2


async def test_http_journal_keeps_safe_account_failure_without_secret_body(tmp_path):
    path = tmp_path / "requests.jsonl"
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda _: httpx.Response(
            403, json={"error": {"code": "AccountOverdueError", "message": "secret-value"}}))) as client:
        budget = collector.RequestBudget(path, stage="ingestion", limit=2)
        await budget.instrument(Encoder(client), "sparse")
        await client.post("https://encoder.invalid", headers={"Authorization": "secret-header"})
        assert budget.summary()["http_failures"][0]["reason"] == "account_overdue"
        budget.close()
    assert "secret" not in path.read_text()


def test_coverage_separates_structural_conflict_semantic_doubt_and_missing_target():
    query = {"source_query_id": "q0", "query": "query q0"}
    ready = collector.coverage_record(query, supervision(uncertain=True), candidate())
    assert ready["loss_eligible"] and ready["semantic_uncertain"]
    conflict = collector.coverage_record(query, supervision(conflict=True), candidate())
    assert conflict["pair_in_union"] and not conflict["loss_eligible"]
    missing = collector.coverage_record(query, supervision(), candidate(ids=("c1",)))
    assert not missing["pair_in_union"] and not missing["loss_eligible"]
    empty = collector.coverage_record(query, supervision(), candidate(status="empty", ids=()))
    assert empty["ranking_input_ready"] and not empty["pair_in_union"]
    assert empty["route_status"]["sparse"] == "empty"


async def test_failure_preserved_and_resume_only_collects_unexecuted_tail(tmp_path, monkeypatch):
    prepare(tmp_path)
    called = []

    async def fake(**kwargs):
        assert set(kwargs) == {"source_query_id", "query", "dataset_ids", "sample_id",
                               "execute_candidates", "fetch_candidate_rows"}
        qid = kwargs["source_query_id"]
        called.append(qid)
        return candidate(qid, status="failed" if qid == "q1" else "ready")

    monkeypatch.setattr("linkrag_eval.runners.exploration_input.collect_exploration_input", fake)
    budget = collector.RequestBudget(tmp_path / "requests.jsonl", stage="train", limit=10)
    first = await collector.collect_queries(tmp_path, "train", execute=None, fetch=None,
                                            resume=False, budget=budget)
    assert first["input_status_counts"] == {"ready": 1, "failed": 1, "not_executed": 1}
    second = await collector.collect_queries(tmp_path, "train", execute=None, fetch=None,
                                             resume=True, budget=budget)
    assert called == ["q0", "q1", "q2"]
    assert second["status"] == "incomplete"
    assert second["input_status_counts"] == {"ready": 2, "failed": 1}
    assert len(list(collector.rows(tmp_path / "candidates/train/inputs.jsonl"))) == 3
    budget.close()


async def test_resume_rejects_query_changes_without_touching_candidates(tmp_path):
    prepare(tmp_path, 1)
    p = tmp_path / "candidates/train"
    collector.write_rows(p / "queries.jsonl", [{"source_query_id": "q0", "query": "changed"}])
    collector.write_rows(p / "inputs.jsonl", [candidate()])
    original = (p / "inputs.jsonl").read_bytes()
    budget = collector.RequestBudget(tmp_path / "requests.jsonl", stage="train", limit=10)
    with pytest.raises(ValueError, match="denominator differs"):
        await collector.collect_queries(tmp_path, "train", execute=None, fetch=None,
                                         resume=True, budget=budget)
    assert (p / "inputs.jsonl").read_bytes() == original
    budget.close()


@pytest.mark.parametrize("count", [0, 1])
async def test_target_claim_refuses_foreign_collection(tmp_path, count):
    class Client:
        async def collection_exists(self, **kwargs):
            assert kwargs == {"collection_name": "eval_target"}
            return True

        async def count(self, **kwargs):
            return SimpleNamespace(count=count)

    with pytest.raises(ValueError, match="Unowned .* target"):
        await collector.claim_storage(tmp_path, None, Client(), {
            "storage": {"qdrant_collection": "eval_target"}})
    assert not (tmp_path / "storage/owner.json").exists()


def test_runtime_change_is_rejected_but_source_revision_is_recordable():
    first = {"route_depths": {"dense": 150}, "code_revision": "a", "worktree_dirty": True}
    collector.validate_runtime(first, {**first, "code_revision": "b"})
    with pytest.raises(ValueError):
        collector.validate_runtime(first, {**first, "route_depths": {"dense": 1}})


async def test_confirmation_stage_is_blocked_before_any_prepared_input_read(tmp_path):
    with pytest.raises(ValueError, match="Confirmation collection"):
        await collector.run(tmp_path, "confirmation", resume=False)


@pytest.mark.parametrize("problem", ["missing_query", "missing_supervision", "wrong_role"])
def test_preflight_rejects_broken_denominator_and_supervision_before_calls(tmp_path, monkeypatch, problem):
    from linkrag_eval.store.ids import eval_chunk_id

    monkeypatch.setattr(collector, "IDENTITY", {**collector.IDENTITY, "corpus_count": 2})
    monkeypatch.setattr(collector, "QUERY_COUNTS", {"train": 2})
    prepare(tmp_path, 2)
    corpus = [{"source_passage_id": "p1", "content": "body1"},
              {"source_passage_id": "p2", "content": "body2"}]
    mapping = [{"source_passage_id": p["source_passage_id"], "dataset_id": 995300,
                "doc_id": 9953000000000 + i, "chunk_id": eval_chunk_id(995300, 9953000000000 + i, 0)}
               for i, p in enumerate(corpus)]
    collector.write_rows(tmp_path / "prepared/corpus.jsonl", corpus)
    collector.write_rows(tmp_path / "prepared/passage-mapping.jsonl", mapping)
    if problem == "missing_query":
        (tmp_path / "prepared/train/queries.jsonl").write_text("")
    elif problem == "missing_supervision":
        (tmp_path / "prepared/train/supervision.jsonl").write_text("")
    else:
        p = tmp_path / "prepared/train/supervision.jsonl"
        p.write_text(p.read_text().replace('"role": "train"', '"role": "confirmation"'))
    with pytest.raises(ValueError, match="denominator|Supervision IDs"):
        collector.validate_prepared_stage(tmp_path, "train", {"counts": {"train": {"query_count": 2}}})
