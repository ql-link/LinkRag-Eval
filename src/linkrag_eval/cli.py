"""LinkRag-Eval 统一命令入口:``linkrag-eval <command>``。

子命令:
- ``config``  打印已解析配置(脱敏)做自检
- ``ingest``  collection.tsv + manifest → eval Qdrant/MySQL(EvalVectorIndexer)
- ``run``     golden → 召回(eval 前缀)→ 检索指标 → 出分

真实组件(rag + 活栈)在各子命令内惰性装配;``app.py`` 只编排抽象。
"""

from __future__ import annotations

import argparse
import asyncio
import sys


def _add_ingest(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser("ingest", help="灌库:collection+manifest → eval namespace")
    p.add_argument("--dataset-id", type=int, required=True)
    p.add_argument("--collection", required=True, help="collection.tsv(pid\\ttext)")
    p.add_argument("--manifest", required=True, help="manifest jsonl(source_id/doc_id/status)")
    p.add_argument("--name", required=True, help="数据集编目名")
    p.add_argument("--source-type", default="opensource")
    p.add_argument("--domain", default=None)
    p.add_argument("--genre", default=None)
    p.add_argument("--batch", type=int, default=25)
    p.add_argument("--limit", type=int, default=None)
    p.add_argument("--init-schema", action="store_true", help="先 create_all 建表(无 alembic 时用)")


def _add_run(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser("run", help="跑召回评测:golden → recall → 指标")
    p.add_argument("--golden", required=True, help="golden jsonl")
    p.add_argument("--run-label", default="run", help="run_id 后缀标签")
    p.add_argument("--top-k", type=int, default=10)
    p.add_argument("--out-dir", default="runs", help="快照/报告输出目录")
    p.add_argument("--precheck", action="store_true", help="跑前校验 golden chunk reference 在库")


async def _do_ingest(args) -> int:
    from linkrag_eval.app import run_ingest
    from linkrag_eval.compute.rag_adapter import RagProductComputer
    from linkrag_eval.store.corpus_repo import EvalCorpusRepo
    from linkrag_eval.store.indexer import EvalVectorIndexer
    from linkrag_eval.store.vector_store import build_eval_vector_store

    repo = EvalCorpusRepo()
    if args.init_schema:
        await repo.init_schema()
    indexer = EvalVectorIndexer(
        computer=RagProductComputer(),
        vector_store=build_eval_vector_store(),
        corpus_repo=repo,
    )
    catalog = {
        "name": args.name, "source_type": args.source_type,
        "domain": args.domain, "genre": args.genre,
    }
    total = await run_ingest(
        args.dataset_id, args.collection, args.manifest,
        indexer=indexer, corpus_repo=repo, catalog=catalog,
        batch=args.batch, limit=args.limit, progress=print,
    )
    print(f"\n灌库完成:{total} 个 chunk 写进 eval namespace")
    return 0


async def _do_run(args) -> int:
    from linkrag_eval.app import format_retrieval_summary, run_eval
    from linkrag_eval.config import get_settings
    from linkrag_eval.metrics.retrieval import default_retrieval_metrics
    from linkrag_eval.retrieval import build_eval_recall_evaluable
    from linkrag_eval.store.result_store import JsonResultStore

    settings = get_settings()
    run_id = f"{args.run_label}-top{args.top_k}"
    fetch_status = None
    if args.precheck:
        from linkrag_eval.store.corpus_repo import EvalCorpusRepo

        fetch_status = EvalCorpusRepo().fetch_status

    result = await run_eval(
        args.golden,
        top_k=args.top_k,
        run_id=run_id,
        evaluable=build_eval_recall_evaluable(args.top_k, settings=settings),
        metrics=default_retrieval_metrics(),
        store=JsonResultStore(args.out_dir),
        settings=settings,
        fetch_status=fetch_status,
        progress=print,
    )
    print("\n" + format_retrieval_summary(result))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="linkrag-eval", description="toLink-Rag 独立评测/质检")
    sub = parser.add_subparsers(dest="command")
    sub.add_parser("config", help="打印已解析配置(脱敏)做自检")
    _add_ingest(sub)
    _add_run(sub)

    args = parser.parse_args(argv)

    if args.command == "config":
        from linkrag_eval.config import get_settings

        s = get_settings()
        masked = "***" if s.judge_api_key else "(空)"
        print(f"qdrant_host     = {s.qdrant_host}")
        print(f"qdrant_prefix   = {s.qdrant_prefix}")
        print(f"qdrant_buckets  = {s.qdrant_bucket_count}")
        print(f"mysql           = {s.db_host}:{s.db_port}/{s.db_name}")
        print(f"judge_model     = {s.judge_model or '(空)'}  api_key={masked}")
        print(f"embed_model     = {s.embed_model}  dim={s.embed_dim}")
        print(f"sparse          = {s.sparse_provider}:{s.sparse_model or '(空)'}")
        print(f"bm25_mode       = {s.bm25_mode}")
        print(f"user_id(route)  = {s.user_id}")
        return 0
    if args.command == "ingest":
        return asyncio.run(_do_ingest(args))
    if args.command == "run":
        return asyncio.run(_do_run(args))

    parser.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
