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
    p.add_argument(
        "--reviewer-model",
        default=None,
        help="门禁复核模型(须 ≠ 生成器;默认同 generator,仅 --gate 时生效)",
    )
    p.add_argument("--hard-out", default=None, help="难例桶 jsonl 输出(回环未命中,单列)")
    p.add_argument("--user-id", type=int, default=None, help="路由租户(默认 EVAL_USER_ID)")
    p.add_argument("--seed", type=int, default=None, help="确定性采样种子")


def _add_run(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser("run", help="跑召回评测:golden → recall → 指标")
    p.add_argument("--golden", required=True, help="golden jsonl")
    p.add_argument("--run-label", default="run", help="run_id 后缀标签")
    p.add_argument("--top-k", type=int, default=10)
    p.add_argument(
        "--dense-top-k",
        type=int,
        default=None,
        help="dense 分路召回 topK(默认 EVAL_RECALL_DENSE_TOP_K)",
    )
    p.add_argument(
        "--sparse-top-k",
        type=int,
        default=None,
        help="sparse 分路召回 topK(默认 EVAL_RECALL_SPARSE_TOP_K)",
    )
    p.add_argument(
        "--dense-score-threshold", type=float, default=None, help="dense 分路分数阈值覆盖"
    )
    p.add_argument(
        "--sparse-score-threshold", type=float, default=None, help="sparse 分路分数阈值覆盖"
    )
    p.add_argument(
        "--fusion-strategy",
        choices=["rrf", "weighted_score"],
        default=None,
        help="融合算法(默认 EVAL_RECALL_FUSION_STRATEGY)",
    )
    p.add_argument("--dense-weight", type=float, default=None, help="weighted_score dense 权重")
    p.add_argument("--sparse-weight", type=float, default=None, help="weighted_score sparse 权重")
    p.add_argument(
        "--bm25-top-k",
        type=int,
        default=None,
        help="BM25 分路召回 topK(默认 EVAL_RECALL_BM25_TOP_K)",
    )
    p.add_argument("--bm25-weight", type=float, default=None, help="weighted_score bm25 权重")
    p.add_argument(
        "--enabled-sources",
        default=None,
        help="本轮启用的召回路由,逗号分隔:dense,sparse,bm25。默认按 EVAL_BM25_MODE 自动选择。",
    )
    p.add_argument("--out-dir", default="runs", help="快照/报告输出目录")
    p.add_argument("--dataset", default="default", help="报告台账的数据集名(趋势分组用)")
    p.add_argument(
        "--baseline",
        default=None,
        help="基线 run_id(读 results/<id>.json 出回归 diff;须先以该 id 跑过)",
    )
    p.add_argument("--precheck", action="store_true", help="跑前校验 golden chunk reference 在库")
    p.add_argument(
        "--require-chunk-references",
        action="store_true",
        help="拒绝 doc-only golden,主评测强制使用 expected_chunk_ids",
    )


def _add_tune_recall(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser("tune-recall", help="参数搜索:dense/sparse topK + score threshold")
    p.add_argument("--golden", required=True, help="golden jsonl")
    p.add_argument("--dataset", default="default", help="报告数据集名")
    p.add_argument("--out-dir", default="runs/tuning", help="CSV/JSON/Markdown 输出目录")
    p.add_argument("--corpus-chunks", type=int, default=None, help="报告展示用语料 chunk 数")
    p.add_argument("--final-top-k", type=int, default=10, help="最终融合截断 topK")
    p.add_argument("--rrf-k", type=int, default=60, help="RRF 平滑常数")
    p.add_argument(
        "--fusion-strategy",
        choices=("rrf", "weighted_score"),
        default="rrf",
        help="本地复算的融合算法",
    )
    p.add_argument("--dense-weight", type=float, default=0.70, help="weighted_score dense 权重")
    p.add_argument("--sparse-weight", type=float, default=0.15, help="weighted_score sparse 权重")
    p.add_argument("--bm25-weight", type=float, default=0.15, help="weighted_score BM25 权重")
    p.add_argument("--dense-top-ks", default="20,50,100,200")
    p.add_argument("--sparse-top-ks", default="5,10,20,50,100")
    p.add_argument("--bm25-top-ks", default="0")
    p.add_argument("--dense-thresholds", default="0,0.1,0.2,0.3,0.4,0.5")
    p.add_argument("--sparse-thresholds", default="0,0.2,0.25,0.3,0.35,0.4")
    p.add_argument("--bm25-thresholds", default="0")
    p.add_argument("--concurrency", type=int, default=4, help="远端分路召回缓存并发")


def _add_bm25_backfill(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser("bm25-backfill", help="从 eval MySQL 语料重建 SQLite FTS5 BM25 sidecar")
    p.add_argument("--dataset-ids", required=True, help="dataset_id 逗号分隔")
    p.add_argument("--batch", type=int, default=500)
    p.add_argument("--sqlite-path", default=None, help="覆盖 EVAL_BM25_SQLITE_PATH")
    p.add_argument("--min-content-chars", type=int, default=0)


def _add_query_rewrite(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser("query-rewrite", help="生成三路Query重写计划并做原始/重写配对评测")
    commands = p.add_subparsers(dest="query_rewrite_command")

    generate = commands.add_parser("generate", help="仅根据原始Query生成结构化三路重写计划")
    generate.add_argument("--golden", required=True, help="原始Query golden JSONL")
    generate.add_argument("--out", required=True, help="重写计划 JSONL 输出")
    generate.add_argument("--report-out", default=None, help="生成统计 JSON 输出")
    generate.add_argument("--limit", type=int, default=None)
    generate.add_argument("--concurrency", type=int, default=None)
    generate.add_argument("--model", default=None, help="覆盖 EVAL_REWRITE_MODEL")
    generate.add_argument(
        "--use-judge-endpoint",
        action="store_true",
        help="仅复用 eval Judge 的端点和凭证，不读取生产模型配置",
    )
    generate.add_argument("--no-resume", action="store_true", help="忽略已有输出并全部重生成")

    evaluate = commands.add_parser("evaluate", help="同轮运行原始/重写Query并输出配对报告")
    evaluate.add_argument("--golden", required=True, help="必须与生成计划时相同的 golden")
    evaluate.add_argument("--plans", required=True, help="query-rewrite generate 输出 JSONL")
    evaluate.add_argument("--out-dir", required=True)
    evaluate.add_argument("--limit", type=int, default=None)
    evaluate.add_argument("--top-k", type=int, default=10)
    evaluate.add_argument("--retries", type=int, default=5, help="每个分路Query最大尝试次数")
    evaluate.add_argument(
        "--original-protected-top-k",
        type=int,
        default=5,
        help="重写侧强制保留原始Hybrid前K个候选",
    )
    evaluate.add_argument(
        "--default-weights",
        action="store_true",
        help="忽略计划动态权重，固定使用0.70/0.15/0.15",
    )
    evaluate.add_argument(
        "--no-candidate-protection",
        action="store_true",
        help="关闭计划中的Dense/Sparse/BM25候选保护",
    )
    evaluate.add_argument(
        "--rewrite-only",
        action="store_true",
        help="重写侧不合并原始Query候选；默认保留原始Query兜底",
    )
    evaluate.add_argument("--precheck", action="store_true")


def _add_ltr(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser("ltr", help="学习型三路融合候选缓存与交叉验证")
    commands = p.add_subparsers(dest="ltr_command")

    cache = commands.add_parser("cache", help="从活栈缓存Tune三路最大候选")
    cache.add_argument("--golden", required=True)
    cache.add_argument("--out", required=True)
    cache.add_argument("--limit", type=int, default=None)
    cache.add_argument("--concurrency", type=int, default=4)
    cache.add_argument("--retries", type=int, default=5)
    cache.add_argument(
        "--query-routing",
        action="store_true",
        help="按冻结 Query 文本分类选择每路候选 TopK",
    )

    cv = commands.add_parser("cross-validate", help="按证据文档做LambdaMART交叉验证")
    cv.add_argument("--cache", required=True)
    cv.add_argument("--candidate-contents", required=True)
    cv.add_argument("--out-dir", required=True)
    cv.add_argument("--folds", type=int, default=5)
    cv.add_argument("--seed", type=int, default=20260716)

    external = commands.add_parser(
        "train-evaluate",
        help="在冻结训练缓存上训练并对另一套Query缓存一次性评测",
    )
    external.add_argument("--train-cache", required=True)
    external.add_argument("--test-cache", required=True)
    external.add_argument("--candidate-contents", required=True)
    external.add_argument("--out-dir", required=True)
    external.add_argument("--n-estimators", type=int, default=24)
    external.add_argument("--seed", type=int, default=20260716)
    external.add_argument("--historical-baseline", type=float, default=None)
    external.add_argument("--blend-alpha", type=float, default=1.0)
    external.add_argument("--protect-baseline-top-k", type=int, default=0)


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
    p.add_argument(
        "--doc-id-base", type=int, required=True, help="doc_id 起始号段(避免与其他集重叠)"
    )
    p.add_argument("--name", required=True, help="数据集编目名(golden id 前缀)")
    p.add_argument("--golden-out", required=True, help="golden jsonl 输出路径")
    p.add_argument("--manifest", required=True, help="灌库 manifest jsonl 输出/读取路径")
    p.add_argument("--user-id", type=int, default=None, help="路由租户(默认 EVAL_USER_ID)")
    p.add_argument("--batch", type=int, default=25)
    p.add_argument("--limit", type=int, default=None, help="只灌前 N 段(试点)")
    p.add_argument("--max-samples", type=int, default=None, help="只转前 N 条 query")
    p.add_argument(
        "--skip-ingest", action="store_true", help="语料已灌过,仅读 --manifest 转换(不连活栈)"
    )
    p.add_argument("--init-schema", action="store_true", help="先 create_all 建表")
    p.add_argument(
        "--reference-granularity",
        choices=["doc", "chunk"],
        default="doc",
        help="golden reference 粒度。chunk 会从 eval_corpus_chunk 映射 expected_chunk_ids",
    )


def _add_golden_v2(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser("golden-v2", help="Golden V2 构建工具")
    v2 = p.add_subparsers(dest="golden_v2_command")

    sp = v2.add_parser(
        "spark-import",
        help="校验并导入 gpt-5.3-codex-spark 离线预生成 bundle",
    )
    sp.add_argument("--bundle", required=True, help="bundle_manifest.json 路径")
    sp.add_argument("--out", required=True, help="标准化 query_seeds.jsonl 输出")
    sp.add_argument("--hard-out", default=None, help="标准化 hard_case_seeds.jsonl 输出")
    sp.add_argument("--rewrite-out", default=None, help="标准化 rewrite_seeds.jsonl 输出")
    sp.add_argument("--corpus-out", default=None, help="标准化 corpus_blueprints.jsonl 输出")
    sp.add_argument("--chunks-out", default=None, help="标准化 chunk_records.jsonl 输出")
    sp.add_argument("--report-out", default=None, help="导入报告 JSON 输出")
    sp.add_argument("--dry-run", action="store_true", help="只校验,不写输出文件")

    cp = v2.add_parser(
        "spark-corpus-export",
        help="将标准化 chunk_records 导出现有 ingest 的 collection/manifest",
    )
    cp.add_argument("--chunks", required=True, help="标准化 chunk_records.jsonl")
    cp.add_argument("--collection", required=True, help="输出 collection.tsv(pid\\ttext)")
    cp.add_argument(
        "--manifest", required=True, help="输出 manifest.jsonl(source_id/doc_id/status/ordinal)"
    )
    cp.add_argument(
        "--dataset-id", type=int, default=None, help="可选:校验 chunk_records 全部属于该 dataset"
    )
    cp.add_argument("--report-out", default=None, help="导出报告 JSON 输出")

    synth = v2.add_parser(
        "synth-corpus",
        help="从 Spark spec JSON 确定性扩写 eval-only 背景语料",
    )
    synth.add_argument("--spec", required=True, help="Spark 生成的 corpus spec JSON")
    synth.add_argument(
        "--dataset-id", type=int, required=True, help="输出 chunk_records 使用的 eval dataset_id"
    )
    synth.add_argument("--target-chunks", type=int, required=True, help="目标 chunk 数")
    synth.add_argument("--out-dir", required=True, help="输出目录")
    synth.add_argument("--seed", type=int, default=20260709)
    synth.add_argument("--batch-id", default=None)
    synth.add_argument(
        "--report-out", default=None, help="报告 JSON 输出;默认 out-dir/synth_report.json"
    )

    seed = v2.add_parser("seed-import", help="导入/清洗真实 query seed(JSONL/TSV/CSV)")
    seed.add_argument("--input", required=True, help="原始 query 文件")
    seed.add_argument("--out", required=True, help="标准化 query_seeds.jsonl 输出")
    seed.add_argument("--source", required=True, help="来源标识,如 log/support/opensource")
    seed.add_argument("--format", default="auto", choices=["auto", "jsonl", "tsv", "csv"])
    seed.add_argument("--query-field", default="query")
    seed.add_argument("--id-field", default=None)
    seed.add_argument("--domain-field", default="domain")
    seed.add_argument("--type-field", default="type_hint")
    seed.add_argument("--dataset-ids-field", default="dataset_ids")
    seed.add_argument("--min-chars", type=int, default=2)
    seed.add_argument("--max-chars", type=int, default=300)
    seed.add_argument(
        "--allow-pii", action="store_true", help="允许包含手机号/邮箱/身份证号的 query"
    )
    seed.add_argument("--report-out", default=None, help="导入报告 JSON 输出")

    preflight = v2.add_parser("pilot-preflight", help="Golden V2 pilot 本地配置/文件预检")
    preflight.add_argument("--seeds", required=True, help="query_seeds.jsonl")
    preflight.add_argument("--dataset-ids", required=True, help="eval dataset_id,逗号分隔")
    preflight.add_argument("--reviewer-model", required=True, help="第二判官模型名")
    preflight.add_argument("--min-seeds", type=int, default=200)
    preflight.add_argument("--no-require-alt-embedding", action="store_true")
    preflight.add_argument("--report-out", default=None, help="preflight JSON 输出")
    preflight.add_argument("--markdown-out", default=None, help="preflight Markdown 输出")

    pilot = v2.add_parser("pilot-plan", help="生成 Golden V2 pilot 五步执行计划和 medium 2w 计划")
    pilot.add_argument("--out-dir", required=True, help="计划输出目录")
    pilot.add_argument("--dataset-ids", required=True, help="eval dataset_id,逗号分隔")
    pilot.add_argument("--reviewer-model", required=True, help="第二判官模型名")
    pilot.add_argument("--raw-query-input", default=None, help="可选:原始真实 query 文件")
    pilot.add_argument("--seeds", default=None, help="可选:已清洗 query_seeds.jsonl")
    pilot.add_argument("--source", default="log")
    pilot.add_argument("--query-field", default="query")
    pilot.add_argument("--id-field", default=None)
    pilot.add_argument("--stage", default="pilot")
    pilot.add_argument("--route-top-n", type=int, default=50)
    pilot.add_argument("--random-n", type=int, default=20)
    pilot.add_argument("--max-candidates-per-query", type=int, default=80)
    pilot.add_argument("--limit-queries", type=int, default=None, help="试跑前 N 条 query")
    pilot.add_argument("--top-k", type=int, default=10)
    pilot.add_argument("--medium-dataset-id-start", type=int, default=992000)
    pilot.add_argument("--medium-target-chunks", type=int, default=20000)
    pilot.add_argument("--no-markdown", action="store_true")

    cand = v2.add_parser(
        "candidate-pool",
        help="构造 Golden V2 候选池(首版纯文件 local BM25 + random)",
    )
    cand.add_argument("--seeds", required=True, help="query_seeds/hard_case_seeds jsonl")
    cand.add_argument("--chunks", required=True, help="标准化 chunk_records.jsonl")
    cand.add_argument("--out", required=True, help="candidate_pool.jsonl 输出")
    cand.add_argument("--report-out", default=None, help="候选池报告 JSON 输出")
    cand.add_argument("--bm25-top-n", type=int, default=50)
    cand.add_argument("--random-n", type=int, default=20)
    cand.add_argument("--seed", type=int, default=13, help="random_neighbor 确定性种子")

    live_cand = v2.add_parser(
        "candidate-pool-live",
        help="构造 Golden V2 活栈候选池(bm25/dense/sparse 分路 + random)",
    )
    live_cand.add_argument("--seeds", required=True, help="query_seeds/hard_case_seeds jsonl")
    live_cand.add_argument("--dataset-ids", required=True, help="eval dataset_id,逗号分隔")
    live_cand.add_argument("--out", required=True, help="candidate_pool.jsonl 输出")
    live_cand.add_argument("--report-out", default=None, help="候选池报告 JSON 输出")
    live_cand.add_argument("--route-top-n", type=int, default=50)
    live_cand.add_argument("--random-n", type=int, default=20)
    live_cand.add_argument(
        "--sources",
        default="bm25,dense,sparse",
        help="分路来源,逗号分隔:bm25,dense,sparse,alt_embedding",
    )
    live_cand.add_argument("--user-id", type=int, default=None, help="默认 EVAL_USER_ID")
    live_cand.add_argument("--seed", type=int, default=13, help="random_neighbor 确定性种子")
    live_cand.add_argument("--min-content-chars", type=int, default=0)
    live_cand.add_argument("--limit-queries", type=int, default=None, help="试跑前 N 条 query")
    live_cand.add_argument(
        "--global-dataset-scope",
        action="store_true",
        help="忽略 seed 自带 dataset_ids,在 --dataset-ids 的完整语料范围构造候选",
    )
    live_cand.add_argument("--alt-cache-path", default=None, help="覆盖 EVAL_ALT_EMBED_SQLITE_PATH")
    live_cand.add_argument(
        "--dense-score-threshold",
        type=float,
        default=0.0,
        help="候选池 dense 分路阈值,默认 0.0 以扩大标注池",
    )
    live_cand.add_argument(
        "--sparse-score-threshold",
        type=float,
        default=0.0,
        help="候选池 sparse 分路阈值,默认 0.0 以扩大标注池",
    )
    live_cand.add_argument(
        "--alt-score-threshold",
        type=float,
        default=None,
        help="候选池 alt_embedding cosine 阈值。默认不按阈值过滤,只取 topN。",
    )

    alt = v2.add_parser("alt-embed-backfill", help="回填 Golden V2 alt embedding SQLite sidecar")
    alt.add_argument("--dataset-ids", required=True, help="eval dataset_id,逗号分隔")
    alt.add_argument("--batch", type=int, default=100)
    alt.add_argument("--sqlite-path", default=None, help="覆盖 EVAL_ALT_EMBED_SQLITE_PATH")
    alt.add_argument("--min-content-chars", type=int, default=0)

    lab = v2.add_parser("label", help="用 eval judge 对 candidate_pool 逐候选判相关性")
    lab.add_argument("--candidates", required=True, help="candidate_pool.jsonl")
    lab.add_argument("--out", required=True, help="judgments.jsonl 输出")
    lab.add_argument("--report-out", default=None, help="标注 QC 报告 JSON 输出")
    lab.add_argument("--max-candidates-per-query", type=int, default=None)
    lab.add_argument("--limit-queries", type=int, default=None, help="试跑前 N 条 query")
    lab.add_argument(
        "--max-concurrency", type=int, default=8, help="每个 query 同时调用判官的最大请求数"
    )

    qc = v2.add_parser("qc", help="分析 judgments 标注质量并输出 QC 门禁报告")
    qc.add_argument("--judgments", required=True, help="judgments jsonl,多个文件用逗号分隔")
    qc.add_argument("--report-out", required=True, help="QC JSON 输出")
    qc.add_argument("--markdown-out", default=None, help="QC Markdown 输出")
    qc.add_argument("--max-random-relevant-rate", type=float, default=0.05)
    qc.add_argument("--max-unresolved-rate", type=float, default=0.30)
    qc.add_argument("--min-queries", type=int, default=1)

    rq = v2.add_parser("review-queue", help="从 judgments 抽取高风险样本复核队列")
    rq.add_argument("--judgments", required=True, help="judgments jsonl,多个文件用逗号分隔")
    rq.add_argument("--out", required=True, help="review_queue.jsonl 输出")
    rq.add_argument("--report-out", default=None, help="review queue 报告 JSON 输出")
    rq.add_argument("--no-random-relevant", action="store_true", help="不抽取 random relevant")
    rq.add_argument("--no-unresolved", action="store_true", help="不抽取 unresolved query")
    rq.add_argument(
        "--no-alt-check", action="store_true", help="不抽取缺少 alt positive 支持的正例"
    )

    rl = v2.add_parser("review-label", help="用第二判官复判 review queue")
    rl.add_argument("--review-queue", required=True, help="review_queue.jsonl")
    rl.add_argument(
        "--candidate-pool", required=True, help="candidate_pool jsonl,多个文件用逗号分隔"
    )
    rl.add_argument("--out", required=True, help="review_judgments.jsonl 输出")
    rl.add_argument("--report-out", default=None, help="复判报告 JSON 输出")
    rl.add_argument(
        "--reviewer-model", required=True, help="第二判官模型名(复用 EVAL_JUDGE_BASE_URL/API_KEY)"
    )
    rl.add_argument("--limit", type=int, default=None, help="试跑前 N 条 review item")

    adj = v2.add_parser("adjudicate", help="将第二判官复判结果合并回主 judgments")
    adj.add_argument("--judgments", required=True, help="原始 judgments jsonl,多个文件用逗号分隔")
    adj.add_argument("--reviews", required=True, help="review_judgments jsonl,多个文件用逗号分隔")
    adj.add_argument("--out", required=True, help="adjudicated_judgments.jsonl 输出")
    adj.add_argument("--report-out", default=None, help="仲裁合并报告 JSON 输出")
    adj.add_argument("--conflict-out", default=None, help="manual_on_conflict 策略下的冲突队列输出")
    adj.add_argument(
        "--policy",
        default="review_overrides",
        choices=["review_overrides", "manual_on_conflict"],
    )

    build = v2.add_parser("build", help="从 judgments 构建 realistic/hard tune/blind golden")
    build.add_argument("--judgments", required=True, help="judgments jsonl,多个文件用逗号分隔")
    build.add_argument("--out-dir", required=True, help="golden 输出目录")
    build.add_argument("--user-id", type=int, default=None, help="默认 EVAL_USER_ID")
    build.add_argument("--tune-ratio", type=float, default=0.70)

    scale = v2.add_parser("scale-plan", help="生成 Golden V2 2w/10w 分批扩容与成本估算计划")
    scale.add_argument(
        "--stage", default="scale_100k", help="阶段名,如 pilot/medium_20k/scale_100k"
    )
    scale.add_argument("--target-chunks", type=int, required=True, help="目标背景库 chunk 总量")
    scale.add_argument("--out-dir", required=True, help="scale_plan.json/md 输出目录")
    scale.add_argument(
        "--dataset-id-start", type=int, required=True, help="新增批次 dataset_id 起点"
    )
    scale.add_argument("--batch-chunks", type=int, default=5000, help="每批生成/入库 chunk 数")
    scale.add_argument("--existing-chunks", type=int, default=None, help="当前已有 chunk 数")
    scale.add_argument("--existing-jsonl", default=None, help="可选:用 JSONL 行数作为已有 chunk 数")
    scale.add_argument(
        "--query-seed-target", type=int, default=1000, help="正式 blind/tune query 种子目标数"
    )
    scale.add_argument("--route-top-n", type=int, default=50, help="候选池每路 topN")
    scale.add_argument("--random-n", type=int, default=20, help="候选池 random 邻居数")
    scale.add_argument(
        "--max-candidates-per-query", type=int, default=None, help="标注前每 query 候选上限"
    )
    scale.add_argument(
        "--avg-chars-per-chunk", type=int, default=900, help="成本估算:平均 chunk 字符数"
    )
    scale.add_argument(
        "--chars-per-token", type=float, default=2.0, help="成本估算:字符/token 换算"
    )
    scale.add_argument("--judge-input-tokens-per-candidate", type=int, default=900)
    scale.add_argument("--judge-output-tokens-per-candidate", type=int, default=120)
    scale.add_argument("--alt-embedding-batch", type=int, default=100)
    scale.add_argument(
        "--no-alt-embedding", action="store_true", help="计划中不包含 alt embedding 回填"
    )
    scale.add_argument("--no-markdown", action="store_true", help="只输出 JSON,不输出 Markdown")


def _add_cleaning(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser("cleaning", help="清洗质检:对应关系表 → 解析回 md → 分桶比对 → 报告")
    p.add_argument("--registry", required=True, help="对应关系表目录(docs.jsonl + rendered.jsonl)")
    p.add_argument("--run-label", default="clean", help="run_id 后缀标签")
    p.add_argument("--out-dir", default="runs", help="报告输出目录")
    p.add_argument("--dataset", default="default", help="报告台账的数据集名")
    p.add_argument("--pdf-backends", default=None, help="PDF 清洗后端枚举(逗号分隔,默认 auto)")
    p.add_argument(
        "--stability-runs",
        type=int,
        default=1,
        help="非确定后端重复清洗次数(算一致率;确定后端设 1)",
    )


async def _do_ingest(args) -> int:
    from linkrag_eval.app import run_ingest
    from linkrag_eval.compute.rag_adapter import RagProductComputer
    from linkrag_eval.config import get_settings
    from linkrag_eval.store.corpus_repo import EvalCorpusRepo
    from linkrag_eval.store.indexer import EvalVectorIndexer
    from linkrag_eval.store.vector_store import build_eval_vector_store

    settings = get_settings()
    repo = EvalCorpusRepo()
    if args.init_schema:
        await repo.init_schema()
    indexer = EvalVectorIndexer(
        computer=RagProductComputer(),
        vector_store=build_eval_vector_store(settings=settings),
        corpus_repo=repo,
        bm25_mode=settings.bm25_mode,
    )
    catalog = {
        "name": args.name,
        "source_type": args.source_type,
        "domain": args.domain,
        "genre": args.genre,
    }
    total = await run_ingest(
        args.dataset_id,
        args.collection,
        args.manifest,
        indexer=indexer,
        corpus_repo=repo,
        catalog=catalog,
        batch=args.batch,
        limit=args.limit,
        progress=print,
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
                reviewer,
                reviewer_model,
                SimpleBM25Retriever(chunk_texts).search,
                chunk_texts,
            )

    spec_kw = {} if args.seed is None else {"seed": args.seed}
    spec = SampleSpec(user_id=user_id, dataset_ids=dataset_ids, n=args.n, **spec_kw)
    report = await run_golden_gen(
        sampler=sampler,
        generator=generator,
        spec=spec,
        out_path=args.out,
        gate_factory=gate_factory,
        hard_path=args.hard_out,
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
    from linkrag_eval.store.db_result_store import EvalDbResultStore
    from linkrag_eval.store.filesystem import FilesystemResultStore

    settings = get_settings()
    if args.dense_top_k is not None:
        settings.recall_dense_top_k = args.dense_top_k
    if args.sparse_top_k is not None:
        settings.recall_sparse_top_k = args.sparse_top_k
    if args.dense_score_threshold is not None:
        settings.recall_dense_score_threshold = args.dense_score_threshold
    if args.sparse_score_threshold is not None:
        settings.recall_sparse_score_threshold = args.sparse_score_threshold
    if args.bm25_top_k is not None:
        settings.recall_bm25_top_k = args.bm25_top_k
    if args.fusion_strategy is not None:
        settings.recall_fusion_strategy = args.fusion_strategy
    if args.dense_weight is not None:
        settings.recall_dense_weight = args.dense_weight
    if args.sparse_weight is not None:
        settings.recall_sparse_weight = args.sparse_weight
    if args.bm25_weight is not None:
        settings.recall_bm25_weight = args.bm25_weight
    enabled_sources = _parse_enabled_sources(args.enabled_sources)
    _normalize_single_route_weight(settings, enabled_sources)
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
        evaluable=build_eval_recall_evaluable(
            args.top_k, settings=settings, enabled_sources=enabled_sources
        ),
        metrics=default_retrieval_metrics(),
        store=store,
        settings=settings,
        fetch_status=fetch_status,
        require_chunk_refs=args.require_chunk_references,
        enabled_sources=enabled_sources,
        progress=print,
    )
    print("\n" + format_retrieval_summary(result))

    # 落快照 + 结构化结果(后者是后续 --baseline 对比的可 reload 源)
    store.save_snapshot(result.snapshot)
    result_path = store.save_result(result)
    await EvalDbResultStore().save_result(
        result, dataset=args.dataset, baseline_run_id=args.baseline
    )

    baseline = None
    if args.baseline:
        baseline = store.load_baseline(args.baseline)
        if baseline is None:
            print(f"提示:未找到基线 {args.baseline}(需先以该 run_id 跑过并落 results/)")

    paths = write_retrieval_reports(
        result,
        args.out_dir,
        run_id=run_id,
        dataset=args.dataset,
        baseline=baseline,
    )
    print(f"结果: {result_path}")
    print("DB台账: eval_run / eval_metric_result")
    print(f"报告: {paths['html']}\n      {paths['json']}")
    return 0


def _parse_enabled_sources(raw: str | None) -> list[str] | None:
    if raw is None:
        return None
    sources = [x.strip() for x in raw.split(",") if x.strip()]
    allowed = {"dense", "sparse", "bm25"}
    unknown = sorted(set(sources) - allowed)
    if unknown:
        raise SystemExit(f"--enabled-sources 包含未知路由:{','.join(unknown)}")
    if not sources:
        raise SystemExit("--enabled-sources 不能为空")
    return sources


def _normalize_single_route_weight(settings, enabled_sources: list[str] | None) -> None:
    """Ensure a weighted-score single-route run cannot be disabled by a zero default."""
    if settings.recall_fusion_strategy != "weighted_score" or not enabled_sources:
        return
    if len(enabled_sources) != 1:
        return

    attribute = {
        "dense": "recall_dense_weight",
        "sparse": "recall_sparse_weight",
        "bm25": "recall_bm25_weight",
    }[enabled_sources[0]]
    setattr(settings, attribute, 1.0)


async def _do_tune_recall(args) -> int:
    from dataclasses import asdict
    import logging

    from linkrag_eval.config import get_settings
    from linkrag_eval.golden.loader import load_golden
    from linkrag_eval.retrieval.tuning import (
        cache_route_hits,
        iter_configs,
        parse_number_list,
        run_grid,
        write_tuning_outputs,
    )

    logging.getLogger("httpx").setLevel(logging.WARNING)
    dense_top_ks = parse_number_list(args.dense_top_ks, cast=int)
    sparse_top_ks = parse_number_list(args.sparse_top_ks, cast=int)
    bm25_top_ks = parse_number_list(args.bm25_top_ks, cast=int)
    dense_thresholds = parse_number_list(args.dense_thresholds, cast=float)
    sparse_thresholds = parse_number_list(args.sparse_thresholds, cast=float)
    bm25_thresholds = parse_number_list(args.bm25_thresholds, cast=float)
    settings = get_settings()
    samples = load_golden(args.golden)
    print(
        "缓存分路候选: "
        f"samples={len(samples)} max_dense_top_k={max(dense_top_ks)} "
        f"max_sparse_top_k={max(sparse_top_ks)}"
    )
    cached = await cache_route_hits(
        samples,
        settings=settings,
        max_dense_top_k=max(dense_top_ks),
        max_sparse_top_k=max(sparse_top_ks),
        max_bm25_top_k=max(bm25_top_ks),
        concurrency=args.concurrency,
        progress=print,
    )
    configs = list(
        iter_configs(
            dense_top_ks=dense_top_ks,
            sparse_top_ks=sparse_top_ks,
            dense_thresholds=dense_thresholds,
            sparse_thresholds=sparse_thresholds,
            bm25_top_ks=bm25_top_ks,
            bm25_thresholds=bm25_thresholds,
            final_top_k=args.final_top_k,
            rrf_k=args.rrf_k,
        )
    )
    print(f"本地评估参数组合:{len(configs)}")
    fusion_weights = {
        "dense": args.dense_weight,
        "sparse": args.sparse_weight,
        "bm25": args.bm25_weight,
    }
    results = run_grid(
        cached,
        configs,
        fusion_strategy=args.fusion_strategy,
        fusion_weights=fusion_weights,
    )
    best = results[0]
    params = {
        "dense_top_ks": dense_top_ks,
        "sparse_top_ks": sparse_top_ks,
        "bm25_top_ks": bm25_top_ks,
        "dense_thresholds": dense_thresholds,
        "sparse_thresholds": sparse_thresholds,
        "bm25_thresholds": bm25_thresholds,
        "final_top_k": args.final_top_k,
        "rrf_k": args.rrf_k,
        "concurrency": args.concurrency,
        "golden": args.golden,
        "corpus_chunks": args.corpus_chunks,
        "fusion": args.fusion_strategy,
        "fusion_weights": fusion_weights,
        "rerank": "none",
    }
    paths = write_tuning_outputs(
        out_dir=args.out_dir,
        dataset=args.dataset,
        results=results,
        cached=cached,
        args=params,
    )
    print("\n最优配置:")
    print(asdict(best))
    print(f"报告: {paths['md']}")
    print(f"HTML: {paths['html']}")
    print(f"数据: {paths['csv']}\n      {paths['json']}")
    return 0


async def _do_bm25_backfill(args) -> int:
    from linkrag_eval.config import get_settings
    from linkrag_eval.store.corpus_repo import EvalCorpusRepo
    from linkrag_eval.store.sqlite_bm25 import (
        SQLiteBm25Point,
        SQLiteBm25Store,
        local_bm25_tokens,
    )

    settings = get_settings()
    dataset_ids = [int(x) for x in args.dataset_ids.split(",") if x.strip()]
    repo = EvalCorpusRepo()
    rows = await repo.fetch_chunks_for_datasets(
        dataset_ids, min_content_chars=args.min_content_chars
    )
    if not rows:
        print("无可回填 chunk。")
        return 0

    path = args.sqlite_path or settings.bm25_sqlite_path
    store = SQLiteBm25Store(
        path,
        coarse_weight=settings.bm25_sqlite_coarse_weight,
        fine_weight=settings.bm25_sqlite_fine_weight,
    )
    await store.ensure_collection()

    total = 0
    for start in range(0, len(rows), args.batch):
        batch = rows[start : start + args.batch]
        points = [
            SQLiteBm25Point(
                chunk_id=row.chunk_id,
                doc_id=row.doc_id,
                user_id=settings.user_id,
                dataset_id=row.dataset_id,
                chunk_type="text",
                tokens=local_bm25_tokens(row.content),
            )
            for row in batch
        ]
        await store.upsert_chunks(points)
        await repo.mark_bm25_indexed([p.chunk_id for p in points], indexed=True)
        total += len(points)
        print(f"  bm25 backfill {total}/{len(rows)} → {path}")

    print(f"\nBM25 SQLite FTS5 回填完成:{total} chunks → {path}")
    return 0


async def _do_query_rewrite(args) -> int:
    import json
    from pathlib import Path

    from linkrag_eval.config import get_settings
    from linkrag_eval.golden.loader import load_golden, precheck

    settings = get_settings()
    samples = load_golden(args.golden)
    if args.limit is not None:
        samples = samples[: max(0, args.limit)]
    if not samples:
        print("错误:Query rewrite 输入为空", file=sys.stderr)
        return 2

    if args.query_rewrite_command == "generate":
        from linkrag_eval.judge.eval_llm import EvalChatClient
        from linkrag_eval.query_rewrite import QueryRewritePlanner, generate_rewrite_plans

        base_url = settings.judge_base_url if args.use_judge_endpoint else settings.rewrite_base_url
        api_key = settings.judge_api_key if args.use_judge_endpoint else settings.rewrite_api_key
        model = (
            args.model
            or settings.rewrite_model
            or (settings.judge_model if args.use_judge_endpoint else "")
        )
        missing = [
            name
            for name, value in (
                ("rewrite base URL", base_url),
                ("rewrite API key", api_key),
                ("rewrite model", model),
            )
            if not str(value or "").strip()
        ]
        if missing:
            print(f"错误:缺少 Query rewrite 配置:{','.join(missing)}", file=sys.stderr)
            return 2
        client = EvalChatClient(
            base_url=base_url,
            api_key=api_key,
            model=model,
            timeout_s=settings.rewrite_timeout_s,
            max_retries=settings.rewrite_max_retries,
            concurrency=settings.rewrite_concurrency,
        )
        planner = QueryRewritePlanner(
            client,
            model=model,
            prompt_version=settings.rewrite_prompt_version,
            temperature=settings.rewrite_temperature,
            max_tokens=settings.rewrite_max_tokens,
        )
        try:
            report = await generate_rewrite_plans(
                samples,
                planner=planner,
                out=Path(args.out),
                report_out=Path(args.report_out) if args.report_out else None,
                concurrency=args.concurrency or settings.rewrite_concurrency,
                resume=not args.no_resume,
                progress=print,
            )
        finally:
            await client.aclose()
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0

    if args.query_rewrite_command == "evaluate":
        from linkrag_eval.query_rewrite.evaluation import (
            PairedRewriteEvaluator,
            evaluate_rewrite_pairs,
            load_rewrite_plans,
        )
        from linkrag_eval.golden.loader import require_chunk_references
        from linkrag_eval.store.corpus_repo import EvalCorpusRepo

        require_chunk_references(samples)
        if args.precheck:
            report = await precheck(samples, EvalCorpusRepo().fetch_status)
            print(report.summary())
            if not report.ok:
                print("错误:Query rewrite golden precheck 失败", file=sys.stderr)
                return 2
        evaluator = PairedRewriteEvaluator(
            settings=settings,
            final_top_k=args.top_k,
            include_original=not args.rewrite_only,
            retries=args.retries,
            use_plan_weights=not args.default_weights,
            use_candidate_protection=not args.no_candidate_protection,
            original_protected_top_k=args.original_protected_top_k,
        )
        payload = await evaluate_rewrite_pairs(
            samples,
            plans=load_rewrite_plans(args.plans),
            evaluator=evaluator,
            out_dir=Path(args.out_dir),
            progress=print,
        )
        print(
            "query rewrite paired result: "
            f"n={payload['samples']} clean={payload['quality']['clean']} "
            f"original_hit@10={payload['original']['hit_at_10']:.4f} "
            f"rewritten_hit@10={payload['rewritten']['hit_at_10']:.4f} "
            f"delta={payload['delta']['hit_at_10']:+.4f}"
        )
        print(f"报告: {Path(args.out_dir) / 'query_rewrite_pair_report.html'}")
        return 0

    print("错误:query-rewrite 需要 generate 或 evaluate 子命令", file=sys.stderr)
    return 2


async def _do_ltr(args) -> int:
    import json
    from pathlib import Path

    if args.ltr_command == "cache":
        from linkrag_eval.config import get_settings
        from linkrag_eval.golden.loader import load_golden, require_chunk_references
        from linkrag_eval.retrieval.learning_to_rank import cache_ltr_candidates

        samples = load_golden(args.golden)
        require_chunk_references(samples)
        if args.limit is not None:
            samples = samples[: max(0, args.limit)]
        report = await cache_ltr_candidates(
            samples,
            settings=get_settings(),
            out=Path(args.out),
            concurrency=args.concurrency,
            retries=args.retries,
            use_query_routing=args.query_routing,
            progress=print,
        )
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0 if report["failed_samples"] == 0 else 1

    if args.ltr_command == "cross-validate":
        from linkrag_eval.retrieval.learning_to_rank import run_ltr_cross_validation

        report = run_ltr_cross_validation(
            Path(args.cache),
            out_dir=Path(args.out_dir),
            candidate_contents_path=Path(args.candidate_contents),
            folds=args.folds,
            seed=args.seed,
        )
        overall = report["overall"]
        print(
            "LTR CV: "
            f"n={overall['n']} "
            f"baseline_hit@10={overall['baseline_hit_at_10']:.4f} "
            f"ltr_hit@10={overall['ltr_hit_at_10']:.4f} "
            f"delta={overall['delta_hit_at_10']:+.4f}"
        )
        print(f"报告: {Path(args.out_dir) / 'ltr_cross_validation.html'}")
        return 0

    if args.ltr_command == "train-evaluate":
        from linkrag_eval.retrieval.learning_to_rank import run_ltr_external_evaluation

        report = run_ltr_external_evaluation(
            Path(args.train_cache),
            Path(args.test_cache),
            out_dir=Path(args.out_dir),
            candidate_contents_path=Path(args.candidate_contents),
            n_estimators=args.n_estimators,
            seed=args.seed,
            historical_baseline_hit_at_10=args.historical_baseline,
            blend_alpha=args.blend_alpha,
            protect_baseline_top_k=args.protect_baseline_top_k,
        )
        overall = report["overall"]
        print(
            "LTR external: "
            f"n={overall['n']} "
            f"baseline_hit@10={overall['baseline_hit_at_10']:.4f} "
            f"ltr_hit@10={overall['ltr_hit_at_10']:.4f} "
            f"delta={overall['delta_hit_at_10']:+.4f}"
        )
        print(f"报告: {Path(args.out_dir) / 'ltr_external_evaluation.html'}")
        return 0

    print(
        "错误:ltr 需要 cache、cross-validate 或 train-evaluate 子命令",
        file=sys.stderr,
    )
    return 2


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
    repo = None
    chunk_lookup = None
    if args.reference_granularity == "chunk":
        from linkrag_eval.store.corpus_repo import EvalCorpusRepo

        repo = EvalCorpusRepo()
        chunk_lookup = repo.fetch_chunk_ids_for_docs
    if not args.skip_ingest:
        from linkrag_eval.compute.rag_adapter import RagProductComputer
        from linkrag_eval.store.corpus_repo import EvalCorpusRepo
        from linkrag_eval.store.indexer import EvalVectorIndexer
        from linkrag_eval.store.vector_store import build_eval_vector_store

        repo = repo or EvalCorpusRepo()
        if args.init_schema:
            await repo.init_schema()
        indexer = EvalVectorIndexer(
            computer=RagProductComputer(),
            vector_store=build_eval_vector_store(settings=settings),
            corpus_repo=repo,
            bm25_mode=settings.bm25_mode,
        )

    report = await run_opensource_golden(
        corpus,
        judgments,
        dataset_id=args.dataset_id,
        user_id=user_id,
        dataset_name=args.name,
        indexer=indexer,
        manifest_path=args.manifest,
        golden_out=args.golden_out,
        doc_id_base=args.doc_id_base,
        graded=graded,
        limit=args.limit,
        max_samples=args.max_samples,
        batch=args.batch,
        skip_ingest=args.skip_ingest,
        reference_granularity=args.reference_granularity,
        chunk_lookup=chunk_lookup,
        progress=print,
    )
    print("\n" + report.summary())
    return 0


async def _do_golden_v2(args) -> int:
    if args.golden_v2_command == "spark-import":
        from linkrag_eval.golden_v2 import import_spark_bundle

        report = import_spark_bundle(
            args.bundle,
            out=args.out,
            hard_out=args.hard_out,
            rewrite_out=args.rewrite_out,
            corpus_out=args.corpus_out,
            chunks_out=args.chunks_out,
            report_out=args.report_out,
            dry_run=args.dry_run,
        )
        print("\n" + report.summary())
        for kind, path in report.output_paths.items():
            print(f"{kind}: {path}")
        if args.dry_run:
            print("dry-run: 未写出文件")
        return 0
    if args.golden_v2_command == "spark-corpus-export":
        from linkrag_eval.golden_v2 import export_spark_corpus

        report = export_spark_corpus(
            args.chunks,
            collection_out=args.collection,
            manifest_out=args.manifest,
            report_out=args.report_out,
            dataset_id=args.dataset_id,
        )
        print("\n" + report.summary())
        print(f"collection: {report.collection_path}")
        print(f"manifest: {report.manifest_path}")
        if report.report_path:
            print(f"report: {report.report_path}")
        return 0
    if args.golden_v2_command == "synth-corpus":
        from linkrag_eval.golden_v2 import synthesize_corpus_from_spec

        report = synthesize_corpus_from_spec(
            args.spec,
            dataset_id=args.dataset_id,
            target_chunks=args.target_chunks,
            out_dir=args.out_dir,
            seed=args.seed,
            batch_id=args.batch_id,
            report_out=args.report_out,
        )
        print("\n" + report.summary())
        print(f"chunk_records: {report.chunk_records_path}")
        print(f"corpus_blueprints: {report.corpus_blueprints_path}")
        print(f"manifest: {report.manifest_path}")
        if report.report_path:
            print(f"report: {report.report_path}")
        return 0
    if args.golden_v2_command == "seed-import":
        from linkrag_eval.golden_v2 import import_query_seeds

        report = import_query_seeds(
            args.input,
            out=args.out,
            source=args.source,
            input_format=args.format,
            query_field=args.query_field,
            id_field=args.id_field,
            domain_field=args.domain_field,
            type_field=args.type_field,
            dataset_ids_field=args.dataset_ids_field,
            min_chars=args.min_chars,
            max_chars=args.max_chars,
            reject_pii=not args.allow_pii,
            report_out=args.report_out,
        )
        print("\n" + report.summary())
        print(f"query_seeds: {report.output_path}")
        if report.report_path:
            print(f"report: {report.report_path}")
        return 0
    if args.golden_v2_command == "pilot-preflight":
        from linkrag_eval.config import get_settings
        from linkrag_eval.golden_v2 import run_pilot_preflight

        dataset_ids = [int(x) for x in args.dataset_ids.split(",") if x.strip()]
        report = run_pilot_preflight(
            settings=get_settings(),
            seeds_path=args.seeds,
            dataset_ids=dataset_ids,
            reviewer_model=args.reviewer_model,
            require_alt_embedding=not args.no_require_alt_embedding,
            min_seed_count=args.min_seeds,
            report_out=args.report_out,
            markdown_out=args.markdown_out,
        )
        print("\n" + report.summary())
        if report.report_path:
            print(f"report: {report.report_path}")
        if report.markdown_path:
            print(f"markdown: {report.markdown_path}")
        return 1 if report.status == "fail" else 0
    if args.golden_v2_command == "pilot-plan":
        from linkrag_eval.golden_v2 import build_pilot_plan

        dataset_ids = [int(x) for x in args.dataset_ids.split(",") if x.strip()]
        report = build_pilot_plan(
            out_dir=args.out_dir,
            dataset_ids=dataset_ids,
            reviewer_model=args.reviewer_model,
            raw_query_input=args.raw_query_input,
            seeds_path=args.seeds,
            source=args.source,
            query_field=args.query_field,
            id_field=args.id_field,
            stage=args.stage,
            route_top_n=args.route_top_n,
            random_n=args.random_n,
            max_candidates_per_query=args.max_candidates_per_query,
            limit_queries=args.limit_queries,
            top_k=args.top_k,
            medium_dataset_id_start=args.medium_dataset_id_start,
            medium_target_chunks=args.medium_target_chunks,
            write_markdown=not args.no_markdown,
        )
        print("\n" + report.summary())
        print(f"plan: {report.plan_path}")
        print(f"script: {report.script_path}")
        if report.markdown_path:
            print(f"markdown: {report.markdown_path}")
        return 0
    if args.golden_v2_command == "candidate-pool":
        from linkrag_eval.golden_v2 import build_candidate_pool

        report = build_candidate_pool(
            args.seeds,
            chunks_path=args.chunks,
            out=args.out,
            report_out=args.report_out,
            bm25_top_n=args.bm25_top_n,
            random_n=args.random_n,
            seed=args.seed,
        )
        print("\n" + report.summary())
        print(f"candidate_pool: {report.output_path}")
        if report.report_path:
            print(f"report: {report.report_path}")
        return 0
    if args.golden_v2_command == "candidate-pool-live":
        from types import SimpleNamespace

        from linkrag_eval.config import get_settings
        from linkrag_eval.golden_v2 import build_live_candidate_pool
        from linkrag_eval.llm.dense_client import DenseEncodeError, build_alt_dense_embedder
        from linkrag_eval.models import QuestionType
        from linkrag_eval.retrieval import build_eval_recall_evaluable
        from linkrag_eval.store.alt_embedding_cache import (
            AltEmbeddingCache,
            alt_embedding_model_key,
        )
        from linkrag_eval.store.corpus_repo import EvalCorpusRepo

        settings = get_settings()
        user_id = args.user_id if args.user_id is not None else settings.user_id
        dataset_ids = [int(x) for x in args.dataset_ids.split(",") if x.strip()]
        sources = [x.strip() for x in args.sources.split(",") if x.strip()]
        if not dataset_ids:
            print("错误:--dataset-ids 不能为空", file=sys.stderr)
            return 2
        if not sources:
            print("错误:--sources 不能为空", file=sys.stderr)
            return 2
        allowed_sources = {"bm25", "dense", "sparse", "alt_embedding"}
        unknown_sources = sorted(set(sources) - allowed_sources)
        if unknown_sources:
            print(f"错误:--sources 包含未知来源:{','.join(unknown_sources)}", file=sys.stderr)
            return 2

        repo = EvalCorpusRepo()
        chunks = await repo.fetch_chunks_for_datasets(
            dataset_ids, min_content_chars=args.min_content_chars
        )
        if not chunks:
            print("错误:指定 dataset 下没有可用 chunk", file=sys.stderr)
            return 2
        settings.recall_fusion_strategy = "rrf"
        settings.recall_dense_score_threshold = args.dense_score_threshold
        settings.recall_sparse_score_threshold = args.sparse_score_threshold
        recall_sources = [source for source in sources if source != "alt_embedding"]
        evaluables = {
            source: build_eval_recall_evaluable(
                args.route_top_n, settings=settings, enabled_sources=[source]
            )
            for source in recall_sources
        }
        for evaluable in evaluables.values():
            evaluable.retries = 1
        alt_searcher = None
        if "alt_embedding" in sources:
            try:
                alt_cache = AltEmbeddingCache(args.alt_cache_path or settings.alt_embed_sqlite_path)
                model_key = alt_embedding_model_key(
                    base_url=settings.alt_embed_base_url,
                    model=settings.alt_embed_model,
                    dim=settings.alt_embed_dim,
                )
                alt_searcher = await _build_alt_embedding_searcher(
                    chunks,
                    embedder=build_alt_dense_embedder(settings),
                    cache=alt_cache,
                    model_key=model_key,
                )
            except DenseEncodeError as exc:
                print(f"错误:alt_embedding 启用失败:{exc}", file=sys.stderr)
                return 2

        async def route_search(query: str, route_dataset_ids: list[int], source: str, top_n: int):
            if source == "alt_embedding":
                assert alt_searcher is not None
                hits = await alt_searcher.search(query, route_dataset_ids, top_n)
                if args.alt_score_threshold is None:
                    return hits
                return [hit for hit in hits if float(hit.score) >= args.alt_score_threshold]
            sample = SimpleNamespace(
                id=f"candidate-{source}",
                query=query,
                user_id=user_id,
                dataset_ids=route_dataset_ids,
                expected_chunk_ids=[],
                expected_doc_ids=None,
                golden_answer=None,
                type=QuestionType.KEYWORD,
            )
            try:
                output = await evaluables[source].run(sample)
            except Exception as exc:
                print(f"提示:{source} 分路候选获取失败,本 query 降级为空:{exc}", file=sys.stderr)
                return []
            return output.ranked[:top_n]

        report = await build_live_candidate_pool(
            args.seeds,
            chunks=chunks,
            route_search=route_search,
            out=args.out,
            report_out=args.report_out,
            sources=sources,
            route_top_n=args.route_top_n,
            random_n=args.random_n,
            seed=args.seed,
            limit_queries=args.limit_queries,
            source_labels={
                "bm25": f"bm25_{settings.bm25_mode}",
                "dense": "current_dense",
                "sparse": "current_sparse",
                "alt_embedding": f"alt_embedding:{settings.alt_embed_model}",
            },
            score_thresholds={
                "dense": args.dense_score_threshold,
                "sparse": args.sparse_score_threshold,
                "alt_embedding": args.alt_score_threshold,
            },
            use_seed_dataset_ids=not args.global_dataset_scope,
        )
        print("\n" + report.summary())
        print(f"candidate_pool: {report.output_path}")
        if report.report_path:
            print(f"report: {report.report_path}")
        return 0
    if args.golden_v2_command == "label":
        from linkrag_eval.config import get_settings
        from linkrag_eval.golden_v2 import label_candidate_pool
        from linkrag_eval.judge.eval_llm import build_eval_chat_client

        settings = get_settings()
        client = build_eval_chat_client(settings)
        try:
            report = await label_candidate_pool(
                args.candidates,
                out=args.out,
                judge_client=client,
                report_out=args.report_out,
                max_candidates_per_query=args.max_candidates_per_query,
                limit_queries=args.limit_queries,
                max_concurrency=args.max_concurrency,
            )
        finally:
            await client.aclose()
        print("\n" + report.summary())
        print(f"judgments: {report.output_path}")
        if report.report_path:
            print(f"report: {report.report_path}")
        return 0
    if args.golden_v2_command == "qc":
        from linkrag_eval.golden_v2 import qc_judgments

        paths = [p.strip() for p in args.judgments.split(",") if p.strip()]
        report = qc_judgments(
            paths,
            report_out=args.report_out,
            markdown_out=args.markdown_out,
            max_random_relevant_rate=args.max_random_relevant_rate,
            max_unresolved_rate=args.max_unresolved_rate,
            min_queries=args.min_queries,
        )
        print("\n" + report.summary())
        print(f"report: {report.output_path}")
        if report.markdown_path:
            print(f"markdown: {report.markdown_path}")
        return 1 if report.status == "fail" else 0
    if args.golden_v2_command == "review-queue":
        from linkrag_eval.golden_v2 import build_review_queue

        paths = [p.strip() for p in args.judgments.split(",") if p.strip()]
        report = build_review_queue(
            paths,
            out=args.out,
            report_out=args.report_out,
            include_random_relevant=not args.no_random_relevant,
            include_unresolved=not args.no_unresolved,
            include_no_alt_support=not args.no_alt_check,
        )
        print("\n" + report.summary())
        print(f"review_queue: {report.output_path}")
        if report.report_path:
            print(f"report: {report.report_path}")
        return 0
    if args.golden_v2_command == "review-label":
        from linkrag_eval.config import get_settings
        from linkrag_eval.golden_v2 import label_review_queue

        settings = get_settings()
        if args.reviewer_model == settings.judge_model:
            print("提示:reviewer-model 与主 judge_model 相同,无法消除同源偏置。", file=sys.stderr)
        client = _build_chat_client(settings, args.reviewer_model)
        try:
            report = await label_review_queue(
                args.review_queue,
                candidate_pool_paths=[
                    p.strip() for p in args.candidate_pool.split(",") if p.strip()
                ],
                out=args.out,
                judge_client=client,
                report_out=args.report_out,
                limit=args.limit,
            )
        finally:
            await client.aclose()
        print("\n" + report.summary())
        print(f"review_judgments: {report.output_path}")
        if report.report_path:
            print(f"report: {report.report_path}")
        return 0
    if args.golden_v2_command == "adjudicate":
        from linkrag_eval.golden_v2 import adjudicate_judgments

        report = adjudicate_judgments(
            [p.strip() for p in args.judgments.split(",") if p.strip()],
            review_paths=[p.strip() for p in args.reviews.split(",") if p.strip()],
            out=args.out,
            report_out=args.report_out,
            conflict_out=args.conflict_out,
            policy=args.policy,
        )
        print("\n" + report.summary())
        print(f"adjudicated_judgments: {report.output_path}")
        if report.report_path:
            print(f"report: {report.report_path}")
        if report.conflict_path:
            print(f"conflicts: {report.conflict_path}")
        return 0
    if args.golden_v2_command == "build":
        from linkrag_eval.config import get_settings
        from linkrag_eval.golden_v2 import build_golden_from_judgments

        settings = get_settings()
        user_id = args.user_id if args.user_id is not None else settings.user_id
        paths = [p.strip() for p in args.judgments.split(",") if p.strip()]
        report = build_golden_from_judgments(
            paths,
            out_dir=args.out_dir,
            user_id=user_id,
            tune_ratio=args.tune_ratio,
        )
        print("\n" + report.summary())
        print(f"out_dir: {report.out_dir}")
        return 0
    if args.golden_v2_command == "scale-plan":
        from linkrag_eval.golden_v2 import build_scale_plan, count_jsonl

        existing_chunks = args.existing_chunks
        if args.existing_jsonl:
            counted = count_jsonl(args.existing_jsonl)
            if existing_chunks is not None and existing_chunks != counted:
                print(
                    f"提示:--existing-chunks={existing_chunks} 与 --existing-jsonl 行数={counted} 不一致,使用 JSONL 行数。",
                    file=sys.stderr,
                )
            existing_chunks = counted
        report = build_scale_plan(
            stage=args.stage,
            target_chunks=args.target_chunks,
            out_dir=args.out_dir,
            dataset_id_start=args.dataset_id_start,
            batch_chunks=args.batch_chunks,
            existing_chunks=existing_chunks or 0,
            query_seed_target=args.query_seed_target,
            route_top_n=args.route_top_n,
            random_n=args.random_n,
            max_candidates_per_query=args.max_candidates_per_query,
            avg_chars_per_chunk=args.avg_chars_per_chunk,
            chars_per_token=args.chars_per_token,
            judge_input_tokens_per_candidate=args.judge_input_tokens_per_candidate,
            judge_output_tokens_per_candidate=args.judge_output_tokens_per_candidate,
            alt_embedding_batch=args.alt_embedding_batch,
            include_alt_embedding=not args.no_alt_embedding,
            write_markdown=not args.no_markdown,
        )
        print("\n" + report.summary())
        print(f"plan: {report.plan_path}")
        if report.markdown_path:
            print(f"markdown: {report.markdown_path}")
        return 0
    if args.golden_v2_command == "alt-embed-backfill":
        from linkrag_eval.config import get_settings
        from linkrag_eval.llm.dense_client import DenseEncodeError, build_alt_dense_embedder
        from linkrag_eval.store.alt_embedding_cache import (
            AltEmbeddingCache,
            alt_embedding_model_key,
        )
        from linkrag_eval.store.corpus_repo import EvalCorpusRepo

        settings = get_settings()
        dataset_ids = [int(x) for x in args.dataset_ids.split(",") if x.strip()]
        if not dataset_ids:
            print("错误:--dataset-ids 不能为空", file=sys.stderr)
            return 2
        repo = EvalCorpusRepo()
        chunks = await repo.fetch_chunks_for_datasets(
            dataset_ids, min_content_chars=args.min_content_chars
        )
        if not chunks:
            print("错误:指定 dataset 下没有可用 chunk", file=sys.stderr)
            return 2
        try:
            embedder = build_alt_dense_embedder(settings)
        except DenseEncodeError as exc:
            print(f"错误:alt_embedding 启用失败:{exc}", file=sys.stderr)
            return 2
        cache = AltEmbeddingCache(args.sqlite_path or settings.alt_embed_sqlite_path)
        model_key = alt_embedding_model_key(
            base_url=settings.alt_embed_base_url,
            model=settings.alt_embed_model,
            dim=settings.alt_embed_dim,
        )
        written = await _backfill_alt_embeddings(
            chunks, embedder=embedder, cache=cache, model_key=model_key, batch=args.batch
        )
        cached = await cache.count(model_key=model_key, dataset_ids=dataset_ids)
        print(
            f"\nAlt embedding 回填完成: written={written} cached={cached} "
            f"chunks={len(chunks)} → {cache.path}"
        )
        return 0
    print("错误:缺少 golden-v2 子命令", file=sys.stderr)
    return 2


async def _build_alt_embedding_searcher(
    chunks,
    *,
    embedder,
    cache=None,
    model_key: str | None = None,
) -> object:
    from linkrag_eval.golden_v2.alt_embedding_search import AltEmbeddingSearcher

    items = list(chunks)
    vectors_by_id = {}
    if cache is not None and model_key is not None:
        vectors_by_id = await cache.fetch_vectors(items, model_key=model_key)
        missing = [c for c in items if c.chunk_id not in vectors_by_id]
        if missing:
            await _backfill_alt_embeddings(
                missing, embedder=embedder, cache=cache, model_key=model_key
            )
            vectors_by_id.update(await cache.fetch_vectors(missing, model_key=model_key))
        vectors = [vectors_by_id[c.chunk_id] for c in items if c.chunk_id in vectors_by_id]
        items = [c for c in items if c.chunk_id in vectors_by_id]
    else:
        vectors = await embedder.aembed([c.content for c in items])
        if len(vectors) != len(items):
            raise RuntimeError(f"alt embedding 数量不符:{len(vectors)} != {len(items)}")
    return AltEmbeddingSearcher(embedder=embedder, chunks=items, vectors=vectors)


async def _backfill_alt_embeddings(
    chunks,
    *,
    embedder,
    cache,
    model_key: str,
    batch: int = 100,
) -> int:
    from linkrag_eval.store.alt_embedding_cache import AltEmbeddingPoint

    items = list(chunks)
    await cache.ensure_schema()
    existing = await cache.fetch_vectors(items, model_key=model_key)
    missing = [c for c in items if c.chunk_id not in existing]
    written = 0
    batch_size = max(1, int(batch))
    for start in range(0, len(missing), batch_size):
        part = missing[start : start + batch_size]
        vectors = await embedder.aembed([c.content for c in part])
        if len(vectors) != len(part):
            raise RuntimeError(f"alt embedding 数量不符:{len(vectors)} != {len(part)}")
        written += await cache.upsert_vectors(
            [
                AltEmbeddingPoint(
                    chunk_id=c.chunk_id,
                    dataset_id=c.dataset_id,
                    doc_id=c.doc_id,
                    content_hash=c.content_hash,
                    vector=vec,
                )
                for c, vec in zip(part, vectors)
            ],
            model_key=model_key,
        )
    return written


async def _do_cleaning(args) -> int:
    from linkrag_eval.cleaning.adapter import CleaningEvaluable
    from linkrag_eval.golden.cleaning_dataset.registry import CleaningRegistry
    from linkrag_eval.reporters import write_cleaning_reports
    from linkrag_eval.runners.cleaning_runner import run_cleaning

    registry = CleaningRegistry.load(args.registry)
    pdf_backends = (
        [b for b in args.pdf_backends.split(",") if b.strip()] if args.pdf_backends else None
    )
    refs = list(registry.iter_rendered_refs(pdf_backends=pdf_backends))
    if not refs:
        print("错误:对应关系表无渲染件(检查 registry 目录)", file=sys.stderr)
        return 2
    print(f"清洗质检 {len(refs)} 个渲染件(stability_runs={args.stability_runs})...")

    evaluable = CleaningEvaluable(stability_runs=args.stability_runs)
    run_id = f"{args.run_label}"
    report, items = await run_cleaning(refs, evaluable, run_id=run_id)

    paths = write_cleaning_reports(report, items, args.out_dir, run_id=run_id, dataset=args.dataset)
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
    _add_golden_v2(sub)
    _add_cleaning(sub)
    _add_run(sub)
    _add_tune_recall(sub)
    _add_bm25_backfill(sub)
    _add_query_rewrite(sub)
    _add_ltr(sub)

    args = parser.parse_args(argv)

    if args.command == "config":
        from linkrag_eval.config import get_settings

        s = get_settings()
        masked = "***" if s.judge_api_key else "(空)"
        print(f"qdrant_host     = {s.qdrant_host}")
        print(f"qdrant_prefix   = {s.qdrant_prefix}")
        print(f"qdrant_buckets  = {s.qdrant_bucket_count}")
        print(f"qdrant_bm25     = {s.qdrant_bm25_collection}/{s.qdrant_bm25_vector_name}")
        print(f"sqlite_bm25     = {s.bm25_sqlite_path}")
        print(f"mysql           = {s.db_host}:{s.db_port}/{s.db_name}")
        print(f"judge_model     = {s.judge_model or '(空)'}  api_key={masked}")
        rewrite_masked = "***" if s.rewrite_api_key else "(空)"
        print(
            f"rewrite_model   = {s.rewrite_model or '(空)'}  "
            f"prompt={s.rewrite_prompt_version} api_key={rewrite_masked}"
        )
        print(f"embed_model     = {s.embed_model}  dim={s.embed_dim}")
        print(
            f"alt_embed_model = {s.alt_embed_provider}:{s.alt_embed_model or '(空)'}  "
            f"dim={s.alt_embed_dim}"
        )
        print(f"alt_embed_cache = {s.alt_embed_sqlite_path}")
        print(f"sparse          = {s.sparse_provider}:{s.sparse_model or '(空)'}")
        print(
            "recall_threshold= "
            f"dense:{s.recall_dense_score_threshold} sparse:{s.recall_sparse_score_threshold}"
        )
        print(
            "recall_top_k    = "
            f"bm25:{s.recall_bm25_top_k} dense:{s.recall_dense_top_k} sparse:{s.recall_sparse_top_k}"
        )
        print(f"bm25_mode       = {s.bm25_mode}")
        print(f"user_id(route)  = {s.user_id}")
        return 0
    if args.command == "ingest":
        return asyncio.run(_run_with_cleanup(_do_ingest(args)))
    if args.command == "golden-gen":
        return asyncio.run(_run_with_cleanup(_do_golden_gen(args)))
    if args.command == "golden-opensource":
        return asyncio.run(_run_with_cleanup(_do_golden_opensource(args)))
    if args.command == "golden-v2":
        return asyncio.run(_run_with_cleanup(_do_golden_v2(args)))
    if args.command == "cleaning":
        return asyncio.run(_run_with_cleanup(_do_cleaning(args)))
    if args.command == "run":
        return asyncio.run(_run_with_cleanup(_do_run(args)))
    if args.command == "tune-recall":
        return asyncio.run(_run_with_cleanup(_do_tune_recall(args)))
    if args.command == "bm25-backfill":
        return asyncio.run(_run_with_cleanup(_do_bm25_backfill(args)))
    if args.command == "query-rewrite":
        return asyncio.run(_run_with_cleanup(_do_query_rewrite(args)))
    if args.command == "ltr":
        return asyncio.run(_run_with_cleanup(_do_ltr(args)))

    parser.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
