"""LinkRag-Eval 统一命令入口:``linkrag-eval <command>``。

子命令:
- ``config``      打印已解析配置(脱敏)做自检
- ``ingest``      collection.tsv + manifest → eval Qdrant/MySQL(EvalVectorIndexer)
- ``golden-gen``  eval 自有语料 → 采样 → LLM 生成 → 自动门禁 → golden jsonl
- ``run``         golden → 召回(eval 前缀)→ 检索指标 → 出分

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


def _add_golden_gen(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser(
        "golden-gen", help="反向合成黄金集:eval 语料 → 采样 → LLM 生成 →(门禁)→ jsonl"
    )
    p.add_argument("--dataset-ids", required=True, help="评测语料 dataset_id(逗号分隔)")
    p.add_argument("--n", type=int, required=True, help="目标黄金集条数")
    p.add_argument("--out", required=True, help="golden jsonl 输出路径")
    p.add_argument("--generator-model", default=None, help="生成器模型(默认 EVAL_JUDGE_MODEL)")
    p.add_argument("--gate", action="store_true", help="启用三信号自动门禁(筛答不出/不自洽)")
    p.add_argument("--reviewer-model", default=None,
                   help="门禁复核模型(须 ≠ 生成器;默认同 generator,仅 --gate 时生效)")
    p.add_argument("--hard-out", default=None, help="难例桶 jsonl 输出(回环未命中,单列)")
    p.add_argument("--user-id", type=int, default=None, help="路由租户(默认 EVAL_USER_ID)")
    p.add_argument("--seed", type=int, default=None, help="确定性采样种子")


def _add_run(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser("run", help="跑召回评测:golden → recall → 指标")
    p.add_argument("--golden", required=True, help="golden jsonl")
    p.add_argument("--run-label", default="run", help="run_id 后缀标签")
    p.add_argument("--top-k", type=int, default=10)
    p.add_argument("--out-dir", default="runs", help="快照/报告输出目录")
    p.add_argument("--dataset", default="default", help="报告台账的数据集名(趋势分组用)")
    p.add_argument("--baseline", default=None,
                   help="基线 run_id(读 results/<id>.json 出回归 diff;须先以该 id 跑过)")
    p.add_argument("--precheck", action="store_true", help="跑前校验 golden chunk reference 在库")


def _add_golden_opensource(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser(
        "golden-opensource",
        help="开源数据集端到端:段落灌 eval 库 → 标注转 GoldenSample(doc 粒度)",
    )
    p.add_argument("--dataset", choices=["dureader", "t2ranking"], required=True)
    p.add_argument("--collection", required=True, help="passage collection tsv(pid\\ttext)")
    p.add_argument("--queries", required=True, help="queries tsv(qid\\tquery)")
    p.add_argument("--qrels", required=True, help="qrels(TREC tsv 或 json)")
    p.add_argument("--dataset-id", type=int, required=True, help="本次灌库 dataset_id")
    p.add_argument("--doc-id-base", type=int, required=True, help="doc_id 起始号段(避免与其他集重叠)")
    p.add_argument("--name", required=True, help="数据集编目名(golden id 前缀)")
    p.add_argument("--golden-out", required=True, help="golden jsonl 输出路径")
    p.add_argument("--manifest", required=True, help="灌库 manifest jsonl 输出/读取路径")
    p.add_argument("--user-id", type=int, default=None, help="路由租户(默认 EVAL_USER_ID)")
    p.add_argument("--batch", type=int, default=25)
    p.add_argument("--limit", type=int, default=None, help="只灌前 N 段(试点)")
    p.add_argument("--max-samples", type=int, default=None, help="只转前 N 条 query")
    p.add_argument("--skip-ingest", action="store_true",
                   help="语料已灌过,仅读 --manifest 转换(不连活栈)")
    p.add_argument("--init-schema", action="store_true", help="先 create_all 建表")


def _add_cleaning(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser("cleaning", help="清洗质检:对应关系表 → 解析回 md → 分桶比对 → 报告")
    p.add_argument("--registry", required=True,
                   help="对应关系表目录(docs.jsonl + rendered.jsonl)")
    p.add_argument("--run-label", default="clean", help="run_id 后缀标签")
    p.add_argument("--out-dir", default="runs", help="报告输出目录")
    p.add_argument("--dataset", default="default", help="报告台账的数据集名")
    p.add_argument("--pdf-backends", default=None,
                   help="PDF 清洗后端枚举(逗号分隔,默认 auto)")
    p.add_argument("--stability-runs", type=int, default=1,
                   help="非确定后端重复清洗次数(算一致率;确定后端设 1)")


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


def _build_chat_client(settings, model: str):
    """按指定 model 装配 eval judge 客户端(复用 EVAL_JUDGE_* 端点/凭证,仅换 model)。"""
    from linkrag_eval.judge.eval_llm import EvalChatClient

    return EvalChatClient(
        base_url=settings.judge_base_url,
        api_key=settings.judge_api_key,
        model=model,
        timeout_s=settings.judge_timeout_s,
        max_retries=settings.judge_max_retries,
        concurrency=settings.judge_concurrency,
    )


async def _do_golden_gen(args) -> int:
    from linkrag_eval.config import get_settings
    from linkrag_eval.golden.gen.gate import AutoQualityGate
    from linkrag_eval.golden.gen.generator import GoldenGenerator
    from linkrag_eval.golden.gen.lexical import SimpleBM25Retriever
    from linkrag_eval.golden.gen.sampler import ChunkSampler, SampleSpec
    from linkrag_eval.runners import run_golden_gen
    from linkrag_eval.store.corpus_repo import EvalCorpusRepo

    settings = get_settings()
    dataset_ids = [int(x) for x in args.dataset_ids.split(",") if x.strip()]
    user_id = args.user_id if args.user_id is not None else settings.user_id
    gen_model = args.generator_model or settings.judge_model
    if not gen_model:
        print("错误:未指定生成器模型(--generator-model 或 EVAL_JUDGE_MODEL)", file=sys.stderr)
        return 2

    sampler = ChunkSampler(EvalCorpusRepo(), user_id=user_id)
    generator = GoldenGenerator(_build_chat_client(settings, gen_model), gen_model)

    gate_factory = None
    if args.gate:
        reviewer_model = args.reviewer_model or gen_model
        if reviewer_model == gen_model:
            print("提示:门禁复核模型与生成器相同,同源偏置只降不消(建议 --reviewer-model 错开)")
        reviewer = _build_chat_client(settings, reviewer_model)

        def gate_factory(chunk_texts):  # noqa: F811 — 闭包捕获 reviewer/model
            return AutoQualityGate(
                reviewer, reviewer_model,
                SimpleBM25Retriever(chunk_texts).search, chunk_texts,
            )

    spec_kw = {} if args.seed is None else {"seed": args.seed}
    spec = SampleSpec(user_id=user_id, dataset_ids=dataset_ids, n=args.n, **spec_kw)
    report = await run_golden_gen(
        sampler=sampler, generator=generator, spec=spec,
        out_path=args.out, gate_factory=gate_factory, hard_path=args.hard_out,
        progress=print,
    )
    print("\n" + report.summary())
    return 0


async def _do_run(args) -> int:
    from linkrag_eval.app import format_retrieval_summary, run_eval
    from linkrag_eval.config import get_settings
    from linkrag_eval.metrics.retrieval import default_retrieval_metrics
    from linkrag_eval.reporters import write_retrieval_reports
    from linkrag_eval.retrieval import build_eval_recall_evaluable
    from linkrag_eval.store.filesystem import FilesystemResultStore

    settings = get_settings()
    run_id = f"{args.run_label}-top{args.top_k}"
    fetch_status = None
    if args.precheck:
        from linkrag_eval.store.corpus_repo import EvalCorpusRepo

        fetch_status = EvalCorpusRepo().fetch_status

    store = FilesystemResultStore(args.out_dir, dataset=args.dataset)
    result = await run_eval(
        args.golden,
        top_k=args.top_k,
        run_id=run_id,
        evaluable=build_eval_recall_evaluable(args.top_k, settings=settings),
        metrics=default_retrieval_metrics(),
        store=store,
        settings=settings,
        fetch_status=fetch_status,
        progress=print,
    )
    print("\n" + format_retrieval_summary(result))

    # 落快照 + 结构化结果(后者是后续 --baseline 对比的可 reload 源)
    store.save_snapshot(result.snapshot)
    result_path = store.save_result(result)

    baseline = None
    if args.baseline:
        baseline = store.load_baseline(args.baseline)
        if baseline is None:
            print(f"提示:未找到基线 {args.baseline}(需先以该 run_id 跑过并落 results/)")

    paths = write_retrieval_reports(
        result, args.out_dir, run_id=run_id, dataset=args.dataset, baseline=baseline,
    )
    print(f"结果: {result_path}")
    print(f"报告: {paths['html']}\n      {paths['json']}")
    return 0


async def _do_golden_opensource(args) -> int:
    from linkrag_eval.config import get_settings
    from linkrag_eval.golden.opensource.datasets import (
        load_dureader_retrieval,
        load_t2ranking,
    )
    from linkrag_eval.runners import run_opensource_golden

    settings = get_settings()
    user_id = args.user_id if args.user_id is not None else settings.user_id
    graded = args.dataset == "t2ranking"
    loader = load_t2ranking if graded else load_dureader_retrieval
    corpus, judgments = loader(args.collection, args.queries, args.qrels)

    indexer = None
    if not args.skip_ingest:
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

    report = await run_opensource_golden(
        corpus, judgments,
        dataset_id=args.dataset_id, user_id=user_id, dataset_name=args.name,
        indexer=indexer, manifest_path=args.manifest, golden_out=args.golden_out,
        doc_id_base=args.doc_id_base, graded=graded, limit=args.limit,
        max_samples=args.max_samples, batch=args.batch,
        skip_ingest=args.skip_ingest, progress=print,
    )
    print("\n" + report.summary())
    return 0


async def _do_cleaning(args) -> int:
    from linkrag_eval.cleaning.adapter import CleaningEvaluable
    from linkrag_eval.golden.cleaning_dataset.registry import CleaningRegistry
    from linkrag_eval.reporters import write_cleaning_reports
    from linkrag_eval.runners.cleaning_runner import run_cleaning

    registry = CleaningRegistry.load(args.registry)
    pdf_backends = (
        [b for b in args.pdf_backends.split(",") if b.strip()]
        if args.pdf_backends else None
    )
    refs = list(registry.iter_rendered_refs(pdf_backends=pdf_backends))
    if not refs:
        print("错误:对应关系表无渲染件(检查 registry 目录)", file=sys.stderr)
        return 2
    print(f"清洗质检 {len(refs)} 个渲染件(stability_runs={args.stability_runs})...")

    evaluable = CleaningEvaluable(stability_runs=args.stability_runs)
    run_id = f"{args.run_label}"
    report, items = await run_cleaning(refs, evaluable, run_id=run_id)

    paths = write_cleaning_reports(
        report, items, args.out_dir, run_id=run_id, dataset=args.dataset
    )
    print(f"\n清洗质检完成:{len(items)} 个渲染件分 {len(report.buckets)} 桶")
    print(f"报告: {paths['html']}\n      {paths['detail']}")
    return 0


async def _run_with_cleanup(coro) -> int:
    try:
        return await coro
    finally:
        from linkrag_eval.store.engine import close_eval_engines

        await close_eval_engines()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="linkrag-eval", description="toLink-Rag 独立评测/质检")
    sub = parser.add_subparsers(dest="command")
    sub.add_parser("config", help="打印已解析配置(脱敏)做自检")
    _add_ingest(sub)
    _add_golden_gen(sub)
    _add_golden_opensource(sub)
    _add_cleaning(sub)
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
        return asyncio.run(_run_with_cleanup(_do_ingest(args)))
    if args.command == "golden-gen":
        return asyncio.run(_run_with_cleanup(_do_golden_gen(args)))
    if args.command == "golden-opensource":
        return asyncio.run(_run_with_cleanup(_do_golden_opensource(args)))
    if args.command == "cleaning":
        return asyncio.run(_run_with_cleanup(_do_cleaning(args)))
    if args.command == "run":
        return asyncio.run(_run_with_cleanup(_do_run(args)))

    parser.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
