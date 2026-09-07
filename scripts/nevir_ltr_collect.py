"""Bounded NevIR ingestion and candidate collection; no model ranking or Test access."""
from __future__ import annotations

import argparse
import asyncio
import fcntl
import json
import logging
import os
from collections import Counter
from contextlib import AsyncExitStack, contextmanager
from datetime import UTC, datetime
from functools import partial
from pathlib import Path
from typing import Any

from linkrag_eval.runners.t2_ingest import _safe_cause_chain
from linkrag_eval.runners.t2_workflow import _write_json_atomic, encoder_semantics

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RUN = ROOT / "runs/post_recall/nevir-ltr-validation-20260907/data-preparation/experiment"
IDENTITY = {"dataset_id": 995300, "doc_id_base": 9953000000000,
            "qdrant_prefix": "eval_nevir_ltr_20260907", "corpus_count": 1761}
LIMITS = {"ingestion": 2200, "train": 4050, "development": 170, "confirmation": 820}
QUERY_COUNTS = {"train": 1896, "development": 76, "confirmation": 374}
ROUTES = ("dense", "sparse", "bm25")
DEPTHS = {"dense": 150, "sparse": 50, "bm25": 100}
THRESHOLDS = {"dense": 0.30, "sparse": 0.20}
WEIGHTS = {"dense": 0.70, "sparse": 0.15, "bm25": 0.15}


def now() -> str:
    return datetime.now(UTC).isoformat()


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def rows(path: Path):
    with path.open(encoding="utf-8") as stream:
        for line in stream:
            yield json.loads(line)


def write_rows(path: Path, values) -> None:
    with path.open("x", encoding="utf-8") as stream:
        for value in values:
            stream.write(json.dumps(value, ensure_ascii=False, allow_nan=False) + "\n")


@contextmanager
def run_lock(root: Path):
    with (root / ".collection.lock").open("a") as stream:
        try:
            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise RuntimeError("This experiment already has an active collector") from None
        try:
            yield
        finally:
            fcntl.flock(stream, fcntl.LOCK_UN)


class RequestLimitExceeded(RuntimeError):
    """Raised before an encoder HTTP attempt would exceed the persisted phase cap."""


class RequestBudget:
    def __init__(self, path: Path, *, stage: str, limit: int):
        self.stage, self.limit = stage, limit
        self.requests: Counter = Counter()
        self.responses: Counter = Counter()
        self.failures: list[dict] = []
        if path.exists():
            for event in rows(path):
                if event["stage"] != stage:
                    raise ValueError("Request journal stage mismatch")
                if event["event"] == "request":
                    self.requests[event["route"]] += 1
                elif event["event"] == "response":
                    self.responses[f"{event['route']}:{event['http_status']}"] += 1
                    if event["http_status"] >= 400:
                        self.failures.append(event)
        if sum(self.requests.values()) > limit:
            raise ValueError("Existing attempts exceed the authorized budget")
        self.stream = path.open("a", encoding="utf-8")

    def record(self, event: dict, *, durable: bool = False) -> None:
        self.stream.write(json.dumps({"stage": self.stage, **event}, allow_nan=False) + "\n")
        self.stream.flush()
        if durable:
            os.fsync(self.stream.fileno())

    async def instrument(self, encoder: Any, route: str) -> None:
        client = await encoder._get_client()

        async def request_hook(request):
            if sum(self.requests.values()) >= self.limit:
                raise RequestLimitExceeded("Encoder attempt limit reached")
            # No await between checking, reserving and persisting this attempt.
            self.requests[route] += 1
            self.record({"event": "request", "route": route,
                         "attempt": sum(self.requests.values())}, durable=True)

        async def response_hook(response):
            self.responses[f"{route}:{response.status_code}"] += 1
            event = {"event": "response", "route": route, "http_status": response.status_code}
            if response.status_code == 403 and route == "sparse":
                await response.aread()
                try:
                    value = response.json()
                except ValueError:
                    value = None
                if (isinstance(value, dict) and isinstance(value.get("error"), dict)
                        and value["error"].get("code") == "AccountOverdueError"):
                    event["reason"] = "account_overdue"
            self.record(event)
            if response.status_code >= 400:
                self.failures.append(event)

        client.event_hooks["request"].append(request_hook)
        client.event_hooks["response"].append(response_hook)

    def summary(self) -> dict:
        return {"hard_limit": self.limit, "physical_encoder_attempts": sum(self.requests.values()),
                "encoder_request_counts": dict(self.requests),
                "encoder_response_counts": dict(self.responses),
                "http_failures": self.failures}

    def close(self):
        self.stream.close()


def bound_settings(root: Path):
    from linkrag_eval.config import get_settings
    settings = get_settings()
    old = read_json(ROOT / "runs/post_recall/nevir-controlled-20260907/run.json")
    if encoder_semantics(settings) != old["encoders"]:
        raise ValueError("Current encoder/BM25 semantics differ from the approved previous run")
    expected = {"embed_batch_size": 10, "embed_concurrency": 4, "sparse_concurrency": 8,
                "user_id": 990001, "sparse_vector_name": "sparse_text"}
    expected.update({f"recall_{k}_top_k": v for k, v in DEPTHS.items()})
    expected.update({f"recall_{k}_score_threshold": v for k, v in THRESHOLDS.items()})
    expected.update({f"recall_{k}_weight": v for k, v in WEIGHTS.items()})
    if any(getattr(settings, key) != value for key, value in expected.items()):
        raise ValueError("Current route/batch settings differ from the approved parameters")
    return settings.model_copy(update={
        "db_url": f"sqlite+aiosqlite:///{root / 'storage/corpus.sqlite3'}",
        "bm25_sqlite_path": str(root / "storage/bm25.sqlite3"),
        "qdrant_prefix": IDENTITY["qdrant_prefix"],
    })


def runtime_metadata(root: Path, settings: Any) -> dict:
    from linkrag_eval.app import _git_state
    from linkrag_eval.runners.t2_workflow import _endpoint
    from linkrag_eval.store.vector_store import resolve_eval_qdrant_collection
    revision, dirty = _git_state()
    return {"encoders": encoder_semantics(settings), "route_depths": DEPTHS,
            "route_thresholds": THRESHOLDS, "fusion_weights": WEIGHTS,
            "rank_origin": 0, "candidate_contract_version": "eval-candidate-contract-v1",
            "candidate_profile": "post-recall-exploration", "fusion_result_limit": 300,
            "outer_batch_size": 25, "dense_batch_size": 10,
            "dense_concurrency": 4, "sparse_concurrency": 8,
            "bm25_effective_text_weights": [1.0, 1.0], "encoder_attempt_limits": LIMITS,
            "user_id": settings.user_id, "sparse_vector_name": settings.sparse_vector_name,
            "code_revision": revision, "worktree_dirty": dirty,
            "storage": {"corpus_sqlite": str(root / "storage/corpus.sqlite3"),
                        "bm25_sqlite": str(root / "storage/bm25.sqlite3"),
                        "qdrant_endpoint": _endpoint(settings.qdrant_host),
                        "qdrant_collection": resolve_eval_qdrant_collection(
                            prefix=settings.qdrant_prefix, bucket_count=settings.qdrant_bucket_count,
                            user_id=settings.user_id)}}


def validate_runtime(previous: dict, current: dict) -> None:
    # A later source change is recorded per phase; it must not silently change inputs/settings.
    ignored = {"code_revision", "worktree_dirty"}
    if {k: v for k, v in previous.items() if k not in ignored} != {
            k: v for k, v in current.items() if k not in ignored}:
        raise ValueError("Runtime settings or storage changed since initial collection")


def validate_prepared_stage(root: Path, stage: str, manifest: dict) -> None:
    """Reject a reduced denominator or invalid supervision before creating network clients."""
    from linkrag_eval.store.ids import eval_chunk_id

    corpus = list(rows(root / "prepared/corpus.jsonl"))
    mapping = list(rows(root / "prepared/passage-mapping.jsonl"))
    if (len(corpus) != IDENTITY["corpus_count"] or len(mapping) != len(corpus)
            or len({x["content"] for x in corpus}) != len(corpus)
            or len({x["source_passage_id"] for x in corpus}) != len(corpus)):
        raise ValueError("Prepared corpus count or anonymous identities differ")
    for position, (body, identity) in enumerate(zip(corpus, mapping, strict=True)):
        doc_id = IDENTITY["doc_id_base"] + position
        if identity != {"source_passage_id": body["source_passage_id"],
                        "dataset_id": IDENTITY["dataset_id"], "doc_id": doc_id,
                        "chunk_id": eval_chunk_id(IDENTITY["dataset_id"], doc_id, 0)}:
            raise ValueError("Prepared passage mapping differs from deterministic ingestion identity")
    if stage == "ingestion":
        return
    queries = list(rows(root / "prepared" / stage / "queries.jsonl"))
    supervision = list(rows(root / "prepared" / stage / "supervision.jsonl"))
    expected = QUERY_COUNTS[stage]
    if manifest["counts"][stage]["query_count"] != expected or len(queries) != expected:
        raise ValueError("Prepared query denominator differs from the approved count")
    if any(set(q) != {"source_query_id", "query"} or not isinstance(q["query"], str)
           or not q["query"].strip() for q in queries):
        raise ValueError("Prepared query must contain only its ID and nonempty original text")
    query_ids = {q["source_query_id"] for q in queries}
    if (len(query_ids) != expected or len(supervision) != expected
            or {s["source_query_id"] for s in supervision} != query_ids
            or any(s["role"] != stage for s in supervision)):
        raise ValueError("Supervision IDs, role or uniqueness differ from the query denominator")
    by_chunk = {x["chunk_id"]: x["source_passage_id"] for x in mapping}
    for item in supervision:
        if any(by_chunk.get(item[f"{side}_chunk_id"]) != item[f"{side}_passage_id"]
               for side in ("preferred", "other")):
            raise ValueError("Supervision references invalid corpus identities")


async def claim_storage(root: Path, settings: Any, client: Any, metadata: dict) -> None:
    storage = root / "storage"
    owner = storage / "owner.json"
    if owner.exists():
        if read_json(owner) != {"identity": IDENTITY, "storage": metadata["storage"]}:
            raise ValueError("Local storage ownership does not match this experiment")
        return
    if storage.exists() and any(storage.iterdir()):
        raise ValueError("Unowned nonempty local storage; refusing to overwrite")
    collection = metadata["storage"]["qdrant_collection"]
    if await client.collection_exists(collection_name=collection):
        count = await client.count(collection_name=collection, exact=True)
        kind = "nonempty" if count.count else "empty"
        raise ValueError(f"Unowned {kind} target Qdrant collection; refusing to claim another target")
    storage.mkdir(exist_ok=True)
    _write_json_atomic(owner, {"identity": IDENTITY, "storage": metadata["storage"]})


def coverage_record(query: dict, supervision: dict, item: dict | None) -> dict:
    result = {key: supervision[key] for key in (
        "source_query_id", "role", "source_group_id", "pair_id", "direction",
        "official_label_available", "structural_conflict", "semantic_uncertain")}
    result.update({"executed": item is not None, "input_status": "not_executed",
                   "ranking_input_ready": False, "pair_in_union": False,
                   "pair_by_route": {s: False for s in ROUTES}, "candidate_count": 0,
                   "supervision_mapping_ready": False, "loss_eligible": False})
    if item is None:
        return result
    if item["query"] != query["query"] or item["source_query_id"] != query["source_query_id"]:
        raise ValueError("Saved query changed between preparation and candidate collection")
    wanted = {supervision["preferred_chunk_id"], supervision["other_chunk_id"]}
    route_ids = {s: {x["chunk_id"] for x in item["routes"][s]} for s in ROUTES}
    candidates = {x["chunk_id"]: x for x in item["candidate_rows"]}
    union = set().union(*route_ids.values())
    mapping = all(candidates.get(supervision[f"{side}_chunk_id"], {}).get("source_passage_id")
                  == supervision[f"{side}_passage_id"] for side in ("preferred", "other"))
    complete = bool(item["ranking_input_ready"]) and set(candidates) == union
    result.update({"input_status": item["status"], "ranking_input_ready": complete,
                   "route_status": item["route_status"], "failed_sources": item["failed_sources"],
                   "pair_in_union": wanted <= union,
                   "pair_by_route": {s: wanted <= ids for s, ids in route_ids.items()},
                   "candidate_count": len(candidates), "supervision_mapping_ready": mapping,
                   "loss_eligible": (result["role"] == "train" and complete and mapping
                                     and wanted <= union and result["official_label_available"]
                                     and not result["structural_conflict"])})
    return result


def summarize_candidates(root: Path, role: str) -> dict:
    prepared = root / "prepared" / role
    queries = {x["source_query_id"]: x for x in rows(prepared / "queries.jsonl")}
    supervision = {x["source_query_id"]: x for x in rows(prepared / "supervision.jsonl")}
    if set(queries) != set(supervision):
        raise ValueError("Query and supervision ID sets differ")
    observed: dict[str, dict] = {}
    path = root / "candidates" / role / "inputs.jsonl"
    if path.exists():
        for item in rows(path):
            qid = item["source_query_id"]
            if qid not in queries or qid in observed:
                raise ValueError("Unknown or duplicate saved query")
            observed[qid] = coverage_record(queries[qid], supervision[qid], item)
    coverage = [observed.get(qid) or coverage_record(q, supervision[qid], None)
                for qid, q in queries.items()]
    out = root / "coverage"
    out.mkdir(exist_ok=True)
    temporary = out / f"{role}.tmp"
    with temporary.open("w", encoding="utf-8") as stream:
        for record in coverage:
            stream.write(json.dumps(record, ensure_ascii=False) + "\n")
    temporary.replace(out / f"{role}.jsonl")
    pairs: dict[str, list[dict]] = {}
    for record in coverage:
        pairs.setdefault(record["pair_id"], []).append(record)
    result = {"query_count": len(queries), "executed_queries": len(observed),
              "input_status_counts": dict(Counter(x["input_status"] for x in coverage)),
              "pair_in_union_queries": sum(x["pair_in_union"] for x in coverage),
              "ranking_input_ready_queries": sum(x["ranking_input_ready"] for x in coverage),
              "loss_eligible_queries": sum(x["loss_eligible"] for x in coverage),
              "paired_both_queries_covered": sum(len(v) == 2 and all(x["pair_in_union"] for x in v)
                                                  for v in pairs.values()),
              "route_empty_counts": {s: sum(x.get("route_status", {}).get(s) == "empty"
                                             for x in coverage) for s in ROUTES}}
    _write_json_atomic(out / f"{role}-summary.json", result)
    return result


async def collect_queries(root: Path, role: str, *, execute: Any, fetch: Any, resume: bool,
                          budget: RequestBudget) -> dict:
    from linkrag_eval.runners.exploration_input import collect_exploration_input
    prepared = root / "prepared" / role
    queries = list(rows(prepared / "queries.jsonl"))
    if len({x["source_query_id"] for x in queries}) != len(queries):
        raise ValueError("Repeated prepared query ID")
    output = root / "candidates" / role
    query_copy = output / "queries.jsonl"
    if query_copy.exists():
        if not resume or list(rows(query_copy)) != queries:
            raise ValueError("Existing query denominator differs or resume was not requested")
    else:
        write_rows(query_copy, queries)
    by_query = {q["source_query_id"]: q["query"] for q in queries}
    path = output / "inputs.jsonl"
    seen = set()
    if path.exists():
        if not resume:
            raise FileExistsError("Existing candidates require explicit resume")
        for item in rows(path):
            qid = item["source_query_id"]
            if qid in seen or item["query"] != by_query[qid]:
                raise ValueError("Unknown, repeated or changed saved query")
            seen.add(qid)
    stopped = False
    with path.open("a", encoding="utf-8") as stream:
        for query in queries:
            qid = query["source_query_id"]
            if qid in seen:
                continue  # Failed attempts also stay recorded; resume only the unexecuted tail.
            if sum(budget.requests.values()) >= budget.limit:
                stopped = True
                break
            item = await collect_exploration_input(
                source_query_id=qid, query=query["query"], dataset_ids=[IDENTITY["dataset_id"]],
                sample_id=qid, execute_candidates=execute, fetch_candidate_rows=fetch)
            stream.write(json.dumps(item, ensure_ascii=False, allow_nan=False) + "\n")
            stream.flush()
            os.fsync(stream.fileno())
            seen.add(qid)
            print(json.dumps({"stage": role, "executed_queries": len(seen),
                              "query_count": len(queries), "status": item["status"],
                              "physical_encoder_attempts": sum(budget.requests.values())}), flush=True)
            if item["failed_sources"] or item["status"] == "failed":
                stopped = True
                break
    summary = summarize_candidates(root, role)
    failed = summary["input_status_counts"].get("failed", 0)
    incomplete = summary["input_status_counts"].get("incomplete", 0)
    return {"status": "completed" if not stopped and not failed and not incomplete else "incomplete",
            **summary}


async def run(root: Path, stage: str, *, resume: bool, confirmation_dispatched: bool = False) -> dict:
    from qdrant_client import AsyncQdrantClient

    from linkrag_eval.compute.rag_adapter import RagProductComputer
    from linkrag_eval.llm.dense_client import build_dense_embedder
    from linkrag_eval.llm.sparse_client import build_sparse_encoder
    from linkrag_eval.retrieval.recall_adapter import execute_candidate_contract_once
    from linkrag_eval.retrieval.recall_factory import build_eval_recall_pipeline
    from linkrag_eval.runners.t2_ingest import ingest_t2_passages
    from linkrag_eval.runners.t2_workflow import migrate_corpus_database
    from linkrag_eval.store.corpus_repo import EvalCorpusRepo
    from linkrag_eval.store.engine import close_eval_engines
    from linkrag_eval.store.indexer import EvalVectorIndexer
    from linkrag_eval.store.sqlite_bm25 import SQLiteBm25Store
    from linkrag_eval.store.vector_store import EvalVectorStore

    root = root.resolve()
    if stage not in LIMITS or (stage == "confirmation" and not confirmation_dispatched):
        raise ValueError("Confirmation collection has not been dispatched")
    manifest = read_json(root / "run.json")
    if manifest.get("identity") != IDENTITY or manifest.get("preparation_status") != "complete":
        raise ValueError("Prepared run identity or completion does not match this experiment")
    validate_prepared_stage(root, stage, manifest)
    settings = bound_settings(root)
    metadata = runtime_metadata(root, settings)
    directory = root / "ingestion" if stage == "ingestion" else root / "candidates" / stage
    with run_lock(root):
        if "collection_runtime" in manifest:
            validate_runtime(manifest["collection_runtime"], metadata)
        elif stage != "ingestion":
            raise ValueError("Ingestion must bind the shared runtime before queries")
        else:
            manifest["collection_runtime"] = metadata
            _write_json_atomic(root / "run.json", manifest)
        if directory.exists() and not resume:
            raise FileExistsError("Existing phase directory; use explicit resume after inspecting its state")
        directory.mkdir(parents=True, exist_ok=resume)
        state_path = directory / "state.json"
        if state_path.exists() and read_json(state_path).get("status") == "completed":
            return read_json(state_path)
        if stage != "ingestion":
            if read_json(root / "ingestion/state.json").get("status") != "completed":
                raise ValueError("Queries require completed shared corpus ingestion")
            if not (root / "storage/owner.json").is_file():
                raise ValueError("Missing storage ownership")
        _write_json_atomic(directory / "run.json", {"identity": IDENTITY, "stage": stage, **metadata})
        budget = RequestBudget(directory / "encoder-requests.jsonl", stage=stage, limit=LIMITS[stage])
        result = {"stage": stage, "status": "running", "started_utc": now(), "pid": os.getpid()}
        _write_json_atomic(state_path, {**result, **budget.summary()})
        try:
            async with AsyncExitStack() as resources:
                resources.push_async_callback(close_eval_engines)
                client = AsyncQdrantClient(url=settings.qdrant_host, api_key=None,
                                           trust_env=False, timeout=60)
                resources.push_async_callback(client.close)
                if stage == "ingestion":
                    await claim_storage(root, settings, client, metadata)
                dense, sparse = build_dense_embedder(settings), build_sparse_encoder(settings)
                resources.push_async_callback(dense.aclose)
                resources.push_async_callback(sparse.aclose)
                await budget.instrument(dense, "dense")
                await budget.instrument(sparse, "sparse")
                migrate_corpus_database(settings.database_url())
                repo = EvalCorpusRepo(url=settings.database_url())
                bm25 = SQLiteBm25Store(settings.bm25_sqlite_path,
                    coarse_weight=settings.bm25_sqlite_coarse_weight,
                    fine_weight=settings.bm25_sqlite_fine_weight)
                vectors = EvalVectorStore(prefix=settings.qdrant_prefix,
                    bucket_count=settings.qdrant_bucket_count, user_id=settings.user_id,
                    qdrant_host=settings.qdrant_host, sparse_vector_name=settings.sparse_vector_name,
                    bm25_store=bm25, bm25_mode=settings.bm25_mode)
                resources.push_async_callback(vectors.aclose)
                await vectors.prepare_collection(vector_size=dense.dim, dataset_id=IDENTITY["dataset_id"],
                                                 on_disk=True)
                if stage == "ingestion":
                    await bm25.ensure_collection()
                    await repo.register_dataset(IDENTITY["dataset_id"],
                        name="NevIR Train+Validation common corpus", source_type="opensource",
                        relevance_type="pairwise", ingestion_ref=str(root / "prepared/corpus.jsonl"),
                        note="1761 anonymous paragraphs; pair/group labels excluded from ingestion")
                    computer = RagProductComputer(dense_encoder=dense, sparse_encoder=sparse)
                    indexer = EvalVectorIndexer(computer=computer, vector_store=vectors, corpus_repo=repo,
                                                with_sparse=True, bm25_mode=settings.bm25_mode)

                    def progress(value):
                        result.update(value)
                        _write_json_atomic(state_path, {**result, **budget.summary()})
                        print(json.dumps({"stage": stage, **value,
                                          "physical_encoder_attempts": sum(budget.requests.values())}), flush=True)

                    value = await ingest_t2_passages(
                        passages=((x["source_passage_id"], x["content"])
                                  for x in rows(root / "prepared/corpus.jsonl")),
                        dataset_id=IDENTITY["dataset_id"], doc_id_base=IDENTITY["doc_id_base"],
                        batch_size=25, corpus_repo=repo, indexer=indexer, vector_store=vectors,
                        bm25_store=bm25, user_id=settings.user_id,
                        expected_passage_count=IDENTITY["corpus_count"], on_progress=progress)
                    result.update(value)
                    result["encoding_inputs"] = await repo.summarize_encoding_inputs(
                        dataset_id=IDENTITY["dataset_id"])
                    result["status"] = "completed"
                else:
                    await vectors.verify_collection_count(dataset_id=IDENTITY["dataset_id"],
                                                           expected_count=IDENTITY["corpus_count"])
                    await repo.verify_dataset_count(dataset_id=IDENTITY["dataset_id"],
                                                     expected_count=IDENTITY["corpus_count"])
                    await bm25.verify_dataset_count(dataset_id=IDENTITY["dataset_id"],
                        user_id=settings.user_id, expected_count=IDENTITY["corpus_count"])
                    pipeline = build_eval_recall_pipeline(settings=settings, dense_encoder=dense,
                                                          sparse_encoder=sparse, qdrant_client=client)
                    execute = partial(execute_candidate_contract_once, pipeline,
                        user_id=settings.user_id, top_k=300, bm25_top_k=100, dense_top_k=150, sparse_top_k=50,
                        dense_score_threshold=0.30, sparse_score_threshold=0.20,
                        enabled_sources=list(ROUTES), required_sources=list(ROUTES), fusion_weights=WEIGHTS,
                        candidate_contract_version="eval-candidate-contract-v1",
                        candidate_profile="post-recall-exploration")
                    result.update(await collect_queries(root, stage, execute=execute,
                        fetch=repo.fetch_candidate_rows, resume=resume, budget=budget))
        except BaseException as exc:  # noqa: BLE001 — persist cancellation/failure without unsafe error text
            result.update({"status": "interrupted" if isinstance(exc, (KeyboardInterrupt, asyncio.CancelledError))
                           else "failed", "cause_chain": _safe_cause_chain(exc)})
            if hasattr(exc, "progress"):
                result["ingest_progress"] = exc.progress
                result["failed_batch"] = exc.failed_batch
                result["cause_chain"] = exc.cause_chain
            if stage != "ingestion":
                result.update(summarize_candidates(root, stage))
        finally:
            result.update({"finished_utc": now(), **budget.summary()})
            _write_json_atomic(state_path, result)
            if stage != "ingestion":
                _write_json_atomic(directory / "summary.json", result)
            budget.close()
        return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, default=DEFAULT_RUN)
    parser.add_argument("--stage", choices=tuple(LIMITS), required=True)
    parser.add_argument("--resume", action="store_true", help="Continue only verified documents/unexecuted query tail")
    parser.add_argument("--confirmation-dispatched", action="store_true",
                        help="Use only after coordinator dispatches confirmation for the selected B")
    args = parser.parse_args()
    logging.disable(logging.CRITICAL)
    try:
        result = asyncio.run(run(args.run_dir, args.stage, resume=args.resume,
                                 confirmation_dispatched=args.confirmation_dispatched))
    except Exception as exc:  # noqa: BLE001 — CLI emits only the safe failure schema
        result = {"status": "failed", "cause_chain": _safe_cause_chain(exc)}
    print(json.dumps(result, ensure_ascii=False), flush=True)
    return 0 if result.get("status") == "completed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
