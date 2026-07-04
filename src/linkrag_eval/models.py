"""评估框架数据模型:枚举 + 贫数据 dataclass。

承载"环节产出"(StageOutput)与"指标结果"(MetricValue/MetricResult)等,
指标计算只认这里的归一化结构,不认生产侧的 RecallResponse / RerankResponse。

硬约束:本模块不 import src.core,零外部运行时依赖(由 .importlinter 强制)。
搬迁自源仓库 ``src/evaluation/models.py``(纯数据,逐字保留)。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class Layer(str, Enum):
    """评估分层,同时用于指标归类、CLI --layers 解析、报告分层。"""

    CLEANING = "cleaning"        # 第0层:数据清洗(文档→md,md round-trip)
    RETRIEVAL = "retrieval"      # 第1层:召回(reference-based 自研)
    RERANK = "rerank"            # 第2层:重排
    GENERATION = "generation"    # 第3层:生成质量(RAG Triad)
    CORRECTNESS = "correctness"  # 第3层:端到端正确性(需 golden_answer)


class QuestionType(str, Enum):
    """黄金集问题类型,用于分桶归因。"""

    KEYWORD = "keyword"
    PARAPHRASE = "paraphrase"
    LONGTAIL = "longtail"
    CROSS_DOC = "cross_doc"


@dataclass(frozen=True)
class RankedHit:
    """归一化排序项:环节产出的统一最小单位。

    无论召回还是重排,都拍平成"按名次排好的 (chunk_id, score)"。
    score 取该环节的排序分(召回 fused_score / 重排 rerank_score,
    降级时取 RRF 顺序分)。
    """

    chunk_id: str
    doc_id: int
    dataset_id: int
    rank: int                    # 0-based 名次(已排序)
    score: float
    # 命中来源集合(dense/sparse/bm25)。融合项可被多路命中,故为集合;
    # 三路重叠率指标直接读它,不依赖 raw。重排后来源不可知则留空集。
    sources: frozenset[str] = frozenset()


@dataclass
class StageOutput:
    """环节产出统一载体:一个结构覆盖检索/重排/生成三层产出。

    检索/重排层指标只读 ranked(+ comparisons);生成层指标读
    answer / contexts;诊断字段进报告不进指标。raw 兜底保留原始响应,
    供适配器调试,指标禁止依赖它。
    """

    layer: Layer
    query: str
    ranked: list[RankedHit]
    # 备选排序:重排层用,键如 "rerank" / "degrade_to_rrf_order",同 run 内对照
    comparisons: dict[str, list[RankedHit]] = field(default_factory=dict)
    # 生成层产出
    answer: str | None = None
    contexts: list[str] = field(default_factory=list)
    # 诊断信息(不进指标,进报告)
    elapsed_ms: int = 0
    per_source_counts: dict[str, int] = field(default_factory=dict)
    failed_sources: list[str] = field(default_factory=list)
    rerank_applied: bool | None = None
    raw: Any = None


@dataclass(frozen=True)
class MetricValue:
    """单指标单样本结果。一个 Metric.compute 可返回多个(如 recall@1/3/5/10)。"""

    name: str                    # "recall@k" / "ndcg@k" / "faithfulness" ...
    layer: Layer
    value: float
    k: int | None = None         # k 类指标的 k;非 k 指标为 None
    n_samples: int = 1           # 判官多次采样时 > 1
    detail: dict[str, Any] = field(default_factory=dict)


@dataclass
class MetricResult:
    """跨样本聚合结果。by_type/by_type_n 供报告出分桶表,小样本桶只作定性参考。"""

    name: str
    layer: Layer
    k: int | None
    mean: float
    n: int                       # 参与聚合的样本数(每桶须标注)
    by_type: dict[QuestionType, float] = field(default_factory=dict)
    by_type_n: dict[QuestionType, int] = field(default_factory=dict)
    # 按语料垂域(eval_dataset.domain)分桶;单域评测退化为一桶,多域可横向对比。
    by_domain: dict[str, float] = field(default_factory=dict)
    by_domain_n: dict[str, int] = field(default_factory=dict)


@dataclass
class Snapshot:
    """配置快照:一次评测运行的可复现判据。

    字段值的实际抓取由 snapshot 填充;top_k 须与召回结果上限同源(单一真相源)。
    """

    run_id: str
    git_sha: str
    # 检索层
    sparse_vector_provider: str  # bge_m3 / bge_m3_http / remote_bge_m3 / ark 等
    top_k: int                   # 融合口径
    score_threshold: float | None  # 历史兼容字段;当前等同 sparse 阈值
    enabled_sources: list[str]   # dense/sparse/bm25
    rrf_k: int
    rerank_top_n: int | None
    # 生成层
    chat_model: str              # 被测系统 CHAT 模型
    judge_model: str             # 判官模型
    generator_model: str         # 黄金集生成器模型
    token_budget: int
    prompt_version: str
    route_score_thresholds: dict[str, float] = field(default_factory=dict)
    route_top_ks: dict[str, int] = field(default_factory=dict)
    fusion_strategy: str = "rrf"
    fusion_weights: dict[str, float] = field(default_factory=dict)

    def validate_model_distinctness(self) -> list[str]:
        """三模型(被测 CHAT / 判官 / 生成器)任意同名即告警,防自评偏置。"""
        warnings: list[str] = []
        roles = [
            ("chat_model", self.chat_model),
            ("judge_model", self.judge_model),
            ("generator_model", self.generator_model),
        ]
        for i, (role_a, model_a) in enumerate(roles):
            for role_b, model_b in roles[i + 1:]:
                if model_a and model_a == model_b:
                    warnings.append(
                        f"{role_a} 与 {role_b} 使用同一模型 '{model_a}',存在自评偏置风险"
                    )
        return warnings


@dataclass
class EvalRequest:
    """一次评测的输入参数。

    top_k=None 时由 runner 回填召回结果上限(单一真相源);仅显式做 top_k
    敏感性实验时才传非 None 值,并由快照如实记录。
    """

    golden_path: str
    layers: list[Layer]
    run_id: str
    top_k: int | None = None
    baseline_run_id: str | None = None


@dataclass
class EvalResult:
    """一次评测的产出:快照 + 聚合指标 + 可选逐样本明细(供归因)。"""

    run_id: str
    snapshot: Snapshot
    metrics: list[MetricResult]
    # 体量大时按需落 json,不进内存汇总
    per_sample: list[dict[str, Any]] = field(default_factory=list)


# ---------------------------------------------------------------------------
# 数据清洗质检(CLEANING 层)专用结构(phase0_5 §五)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CleaningPair:
    """清洗层 StageOutput.raw 载体:参考 md 与清洗产出 md 的一对。

    指标 metrics/cleaning.py 只读这两份 md 文本(解析成块序列后比对),
    不依赖 parser 内部状态——保持"指标读归一化字段、可纯函数单测"。
    """

    ref: str                          # 原始标准 md(参考真值)
    produced: str                     # parser 清洗回的 md
    ok: bool = True                   # 清洗是否成功返回(异常/超时为 False)
    repeats: tuple[str, ...] = ()     # 非确定后端多次清洗的额外输出(供 stability)


@dataclass
class CleaningTextScore:
    completeness: float          # 文本完整性 / recall
    noise: float                 # 文本噪声 / 1-precision


@dataclass
class CleaningHeadingScore:
    recall: float                # 标题识别完整率(是否识别到所有标题)
    false_rate: float            # 误识别率(正文/页眉误判为标题)
    level_consistency_abs: float  # 层级绝对一致率
    level_consistency_rel: float  # 层级相对结构一致率(允许统一偏移)
    missed: list[str] = field(default_factory=list)   # 漏识别清单(排查用明细)


@dataclass
class CleaningTableScore:
    mode_dist: dict[str, int] = field(default_factory=dict)  # {md/image/json: 数量}
    md_cell_f1: float | None = None       # 模式①:单元格对应 F1
    json_corr_f1: float | None = None     # 模式③:对应关系 F1
    image_position_ok: float | None = None  # 模式②:上下文位置正确率
    image_completeness: float | None = None  # 模式②:完整度(弱信号,需 OCR;否则 None)


@dataclass
class CleaningImageScore:
    recall: float                # 图片识别完整率
    false_rate: float            # 图片误识别率
    context_position_ok: float   # 上下文位置正确率(前驱/后继块锚点)
    misplaced: list[str] = field(default_factory=list)  # 位置错的图(排查用明细)


@dataclass
class CleaningQcItem:
    """单文档明细:一次"一个 md × 一种 (format, backend)"的质检结果(§5.1)。"""

    sample_id: str
    format: str                  # pdf / docx / html / md
    pdf_backend: str | None      # 仅 PDF;其余为 None
    clean_ms: int                # 数据清洗时间(一等指标)
    ok: bool                     # 清洗是否成功返回
    text: CleaningTextScore
    heading: CleaningHeadingScore
    table: CleaningTableScore
    image: CleaningImageScore
    list_fidelity: float
    order_fidelity: float
    stability: float = 1.0       # 多次清洗一致率(非确定后端 <1)
    artifacts: dict[str, Any] = field(default_factory=dict)


@dataclass
class CleaningBucket:
    """按 (format, pdf_backend) 聚合的一个桶(§5.2)。每个 metric 即一条 eval_metric_result。"""

    format: str
    pdf_backend: str | None
    n: int
    metrics: dict[str, float] = field(default_factory=dict)


@dataclass
class CleaningQcReport:
    """跨样本聚合:按 (format, pdf_backend) 分桶,供报告与回归(§5.2)。"""

    run_id: str
    snapshot: dict[str, Any] = field(default_factory=dict)
    buckets: list[CleaningBucket] = field(default_factory=list)
