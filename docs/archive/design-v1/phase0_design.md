# 阶段 0 · 地基层 — 设计文档

> **归档文档：仅供追溯，不是当前权威依据。** 替代关系见 [归档说明](../README.md)。

> 状态：设计稿（`.specs/rag-quality-eval/`，git-ignored）
> 上游：[framework_design.md](framework_design.md)（总架构）、[technical_design.md](technical_design.md)（五层评估点口径）
> 范围：评估框架最底层——抽象端口 `contracts/`、数据模型 `models.py`、工程地基（`[eval]` extra / import-lint / 测试布局 / 冻结语料）。
> 目标：定准这两层的**接口与语义**，使阶段 1 起的所有模块只依赖这里，互不直连。本阶段产出零外部依赖、可单测。
>
> ⚠️ **存储口径已更新（权威见 [eval_storage_design.md](eval_storage_design.md)）**：冻结评测语料进评测自持
> **`eval_corpus_chunk`（EvalBase）**，不入生产 `kb_document_chunk`；`user_id` 为路由常量 `EVAL_USER_ID`、
> 非租户隔离。

---

## 一、结论先行

阶段 0 只交付**抽象与数据结构**，不含任何业务逻辑、不碰活栈。两条设计主线：

1. **`contracts/` 是全框架唯一的依赖汇聚点。** `metrics` / `adapters` / `runners` 一律只 import `contracts` 与 `models`，彼此之间不直接 import。新增环节 = 实现 `contracts` 里的协议，不改动既有模块。
2. **`models.py` 用贫数据结构（dataclass）承载"环节产出"与"指标结果"。** 关键是一个能同时表达检索/重排/生成三层产出的 **`StageOutput`**，让指标计算与具体环节解耦——指标只认归一化后的排序列表与答案文本，不认 `RecallResponse` 还是 `RerankResponse`。

依赖方向（硬约束）：`contracts` 不依赖任何其他评估模块；`models` 仅依赖 `contracts` 的枚举；二者都**不** import `src.core`（适配器才连 core，属阶段 1）。

---

## 二、模块清单与产出

```
src/evaluation/
├── __init__.py
├── contracts/
│   ├── __init__.py          # 汇总导出全部协议
│   ├── evaluable.py         # Evaluable：被评测环节的统一调用面
│   ├── metric.py            # Metric：指标计算协议
│   ├── judge.py             # Judge：LLM-as-judge 抽象
│   ├── dataset.py           # Sample / Dataset 协议
│   └── store.py             # ResultStore 协议
└── models.py                # 枚举 + StageOutput + MetricValue/Result + EvalRequest/Result + Snapshot

tests/unit/evaluation/
├── __init__.py
├── test_models.py           # dataclass 构造/默认值/序列化
└── test_contracts.py        # 协议可被 mock 实现、类型契约自洽
```

工程地基（非代码模块，本阶段一并落）：`pyproject.toml` 的 `[eval]` extra、CI import-lint 规则、`tests/unit/evaluation/` 目录、冻结评测语料/租户。详见 §六。

---

## 三、数据模型设计（`models.py`）

### 3.1 枚举

```python
class Layer(str, Enum):
    CLEANING = "cleaning"        # 数据清洗质量（文档→md，md round-trip，见 phase0_5_cleaning_quality_design）
    RETRIEVAL = "retrieval"      # 第1层：召回（reference-based 自研）
    RERANK = "rerank"            # 第2层：重排
    GENERATION = "generation"    # 第3层：生成质量（RAG Triad）
    CORRECTNESS = "correctness"  # 第3层：端到端正确性（需 golden_answer）

class QuestionType(str, Enum):
    KEYWORD = "keyword"
    PARAPHRASE = "paraphrase"
    LONGTAIL = "longtail"
    CROSS_DOC = "cross_doc"
```

`Layer` 同时用于指标归类、CLI `--layers` 解析、报告分层；`QuestionType` 用于分桶归因（黄金集 `type` 字段）。

### 3.2 `RankedHit` — 归一化排序项

环节产出的统一最小单位。无论召回还是重排，都拍平成"按名次排好的 (chunk_id, score)"，指标只认它。

```python
@dataclass(frozen=True)
class RankedHit:
    chunk_id: str
    doc_id: int
    dataset_id: int
    rank: int                       # 0-based 名次（已排序）
    score: float                    # 该环节的排序分（fused_score 或 rerank_score）
    sources: frozenset[str] = frozenset()   # 命中来源集合（dense/sparse/bm25），融合项可多源
```

> 由适配器（阶段 1）从生产的 `RecallHit` / `RerankedHit` 映射而来：召回取 `fused_score`，重排取 `rerank_score`（降级时取 RRF 顺序分）。
>
> **`sources` 为集合而非单值**：一个融合后的 chunk 可能同时被多路命中（`RecallHit.scores` 中非 `None` 的路即命中路），单值无法表达。适配器把"非 None 的路集合"填入 `sources`，使三路重叠率指标直接读归一化字段，**不依赖 `raw`**（兑现"指标只认 `ranked`"的解耦原则）。重排后若来源不可知则留空集。

### 3.3 `StageOutput` — 环节产出统一载体

**本阶段最关键的抽象**。一个结构覆盖三层产出，指标据此计算，与具体环节解耦。

```python
@dataclass
class StageOutput:
    layer: Layer
    query: str
    ranked: list[RankedHit]                       # 主排序列表（检索/重排层指标的输入）
    # 备选排序：重排层用，键如 "rerank" / "degrade_to_rrf_order"，同 run 内对照
    comparisons: dict[str, list[RankedHit]] = field(default_factory=dict)
    # 生成层产出
    answer: str | None = None
    contexts: list[str] = field(default_factory=list)   # assemble_context 纳入的正文块
    # 诊断信息（不进指标，进报告）
    elapsed_ms: int = 0
    per_source_counts: dict[str, int] = field(default_factory=dict)
    failed_sources: list[str] = field(default_factory=list)
    rerank_applied: bool | None = None
    raw: Any = None                               # 原始响应，留作适配器/调试，指标不依赖
```

设计理由：检索/重排层指标只读 `ranked`（+ `comparisons`）；生成层指标读 `answer` / `contexts`；诊断字段（延迟、三路计数、降级标志）进报告不进指标。`raw` 兜底，避免信息丢失，但禁止指标依赖它（保解耦）。

### 3.4 `MetricValue` — 单指标单样本结果

```python
@dataclass(frozen=True)
class MetricValue:
    name: str                       # "recall@k" / "ndcg@k" / "faithfulness" ...
    layer: Layer
    value: float
    k: int | None = None            # k 类指标的 k；非 k 指标为 None
    n_samples: int = 1              # 判官多次采样时 > 1
    detail: dict[str, Any] = field(default_factory=dict)  # 可选明细（命中位置、判官理由等）
```

一个 `Metric.compute` 可返回多个 `MetricValue`（如 recall@1/3/5/10 一次产出）。

### 3.5 `MetricResult` — 跨样本聚合

```python
@dataclass
class MetricResult:
    name: str
    layer: Layer
    k: int | None
    mean: float
    n: int                          # 参与聚合的样本数（每桶须标注，§小样本审慎）
    by_type: dict[QuestionType, float] = field(default_factory=dict)  # 分桶均值
    by_type_n: dict[QuestionType, int] = field(default_factory=dict)  # 分桶样本量
```

报告按 `by_type` + `by_type_n` 出分桶表；小样本桶只作定性参考（口径见 technical_design §七.6）。

### 3.6 `Snapshot` — 配置快照

```python
@dataclass
class Snapshot:
    run_id: str
    git_sha: str
    # 检索层
    sparse_vector_provider: str     # bge_m3 / bge_m3_http / remote_bge_m3（三态覆盖）
    top_k: int                      # 融合口径，须 = RECALL_RESULT_LIMIT
    score_threshold: float | None
    enabled_sources: list[str]      # dense/sparse/bm25
    rrf_k: int
    rerank_top_n: int | None
    # 生成层
    chat_model: str                 # 被测系统 CHAT 模型
    judge_model: str                # 判官模型
    generator_model: str            # 黄金集生成器模型
    token_budget: int
    prompt_version: str
    def validate_model_distinctness(self) -> list[str]: ...  # 三模型同名即告警，防自评偏置
```

`validate_model_distinctness` 在阶段 0 仅定义契约（返回告警列表），实际抓取由阶段 1 的 `snapshot.py` 填充。

### 3.7 `EvalRequest` / `EvalResult`

```python
@dataclass
class EvalRequest:
    golden_path: str
    layers: list[Layer]
    run_id: str
    top_k: int | None = None        # None=取 settings.RECALL_RESULT_LIMIT（单一真相源）
    baseline_run_id: str | None = None

@dataclass
class EvalResult:
    run_id: str
    snapshot: Snapshot
    metrics: list[MetricResult]
    # 可选逐样本明细，供归因；体量大时按需落 json 不进内存汇总
    per_sample: list[dict[str, Any]] = field(default_factory=list)
```

> **top_k 单一真相源**：融合口径的 top_k 一律以 `settings.RECALL_RESULT_LIMIT`（=20）为准。`EvalRequest.top_k=None` 时由 runner 回填该值，`Snapshot.top_k` 也记录同一来源——三处不各立默认值，杜绝口径漂移。仅当显式做 top_k 敏感性实验时才在 `EvalRequest` 传非 None 值，并由快照如实记录。

---

## 四、抽象端口设计（`contracts/`）

全部用 `typing.Protocol`（结构化子类型），适配器/指标无需显式继承，只要签名吻合即可，降低耦合。

### 4.1 `dataset.py` — Sample / Dataset

```python
@runtime_checkable
class Sample(Protocol):
    id: str
    query: str
    user_id: int
    dataset_ids: list[int]
    expected_chunk_ids: list[str]
    expected_doc_ids: list[int] | None
    golden_answer: str | None
    type: QuestionType

@runtime_checkable
class Dataset(Protocol):
    def __iter__(self) -> Iterator[Sample]: ...
    def __len__(self) -> int: ...
```

> 具体的 `GoldenSample`（jsonl schema + 加载校验）在阶段 1 的 `golden/schema.py` 实现，须满足此 `Sample` 协议。本阶段只定协议，不定实现。

### 4.2 `evaluable.py` — 被评测环节统一调用面

```python
@runtime_checkable
class Evaluable(Protocol):
    layer: Layer
    async def run(self, sample: Sample, *, upstream: StageOutput | None = None) -> StageOutput: ...
```

语义：`run` 拿一个样本（重排/生成层还需上游 `StageOutput`，如重排吃召回结果），调用对应生产模块，归一化成 `StageOutput`。**所有对 `src.core` 的调用都收敛在 Evaluable 的实现（即 `adapters/`）里**——这是框架对生产代码的唯一接缝。`async` 因生产入口（`RecallPipeline.execute` 等）均为协程。

### 4.3 `metric.py` — 指标计算

```python
@runtime_checkable
class Metric(Protocol):
    name: str
    layer: Layer
    requires_judge: bool            # 生成层为 True
    requires_golden_answer: bool    # CORRECTNESS 层为 True
    async def compute(
        self, sample: Sample, output: StageOutput, *, judge: "Judge | None" = None
    ) -> list[MetricValue]: ...
```

约定：**协议统一为 `async def compute`**，runner 一律 `await`，无需按层分派。理由：生成层须 `await judge`，而一个 Protocol 不能既同步又异步；检索/重排层声明 `async` 但内部是纯函数（不读 `judge`、不碰 IO），无副作用、可单测、进 PR 门禁，`async` 只是签名统一的代价。如此**阶段 1 起的指标与 runner 不必在阶段 3 回改协议**（兑现本阶段 DoD#6）。`requires_judge` / `requires_golden_answer` 仅用于 runner 校验前置（判官就绪、黄金集带答案），不用于分派同步/异步。

### 4.4 `judge.py` — LLM-as-judge 抽象

```python
@dataclass(frozen=True)
class JudgeResult:
    score: float
    reasoning: str
    n_samples: int

@runtime_checkable
class Judge(Protocol):
    model_name: str
    async def score(
        self, criterion: str, *, query: str, answer: str,
        contexts: list[str], golden_answer: str | None = None,
    ) -> JudgeResult: ...
```

约定：判官 `temperature=0`，关键指标多次采样取均值（`n_samples` 记入结果）。实现（含惰性导入 RAGAS / 接 `ModelFactory`）在阶段 3，本阶段只定契约，**不引入任何判官依赖**。

### 4.5 `store.py` — 产物读写

```python
@runtime_checkable
class ResultStore(Protocol):
    def save_snapshot(self, snapshot: Snapshot) -> None: ...
    def save_report(self, run_id: str, content: str) -> None: ...
    def load_baseline(self, run_id: str) -> EvalResult | None: ...
```

落地实现（写 `.specs`）是阶段 1 的 `storage/filesystem.py`，须满足此协议。

---

## 五、模块关系（阶段 0 内部 + 对未来的约束）

```
            ┌──────────────┐
            │  models.py   │  枚举 + dataclass（贫数据）
            └──────┬───────┘
                   │ import
            ┌──────▼───────┐
            │  contracts/  │  Protocol（Evaluable/Metric/Judge/Dataset/Store）
            └──────┬───────┘
   ┌───────────────┼────────────────┐   （阶段1+ 实现，均只依赖上面两层）
   ▼               ▼                ▼
adapters/       metrics/         runners/
(实现Evaluable) (实现Metric)     (组装二者)
```

铁律：`adapters` 与 `metrics` **互不 import**，只认 `contracts`/`models`；`runners` 是唯一组装点。`contracts`/`models` 不 import `src.core`。

---

## 六、工程地基

### 6.1 `[eval]` extra（依赖隔离）

`pyproject.toml` 加可选依赖组 `[project.optional-dependencies] eval = [...]`。阶段 0 该组**为空或仅含测试桩**——抽象层零外部依赖。判官依赖（RAGAS 等）阶段 3 才加入此组，惰性 import、生产镜像不装。

### 6.2 import-lint 守依赖方向

CI 加一条规则，禁止生产路径反向依赖评估框架：

- 禁止 `src/api/**`、`src/core/**`、`src/services/**`、`src/mq/**` import `src.evaluation`。
- 禁止 `src/evaluation/contracts/**` 与 `src/evaluation/models.py` import `src.core`。

可用 `import-linter` 或一段轻量 AST 检查脚本挂进 pre-commit / CI。

### 6.3 测试布局

`tests/unit/evaluation/`：阶段 0 覆盖 `models` 的构造/默认值/（如需）序列化，以及用 mock 实现验证各 `Protocol` 契约自洽。纯函数、无外部依赖，进 PR 门禁。

### 6.4 冻结评测语料/租户（R2，最先动手）

非代码但阻塞召回以上所有环节：设一份**只读、冻结、专供评测**的 corpus/租户（固定 `user_id` + `dataset_ids`），与生产隔离；记录其某次 ingestion 快照，供阶段 1 的黄金集 `expected_chunk_ids` 绑定。本阶段先确定租户 id 与语料范围并文档化，灌数可与阶段 1 并行。

---

## 七、完成判据（Definition of Done）

1. `src/evaluation/contracts/` 与 `models.py` 落地，零 `src.core` 依赖、零外部运行时依赖。
2. `tests/unit/evaluation/` 下 `models`/`contracts` 单测通过，进 PR 门禁。
3. import-lint 规则就位并在 CI 生效。
4. `[eval]` extra 在 `pyproject.toml` 声明（阶段 0 可为空）。
5. 冻结评测语料/租户的 id 与范围已确定并记入 `.specs`。
6. 阶段 1 可仅依赖 `contracts`/`models` 开工，无需回改本阶段。

---

## 八、本阶段不做（划清边界）

- 不实现任何 `Evaluable`/`Metric`/`Judge`/`ResultStore` 的**具体类**（属阶段 1+）。
- 不 import `src.core`、不调任何生产模块、不碰 MySQL/Qdrant/ES/LLM。
- 不引入 RAGAS 或任何判官依赖。
- 不写 CLI 业务逻辑（`scripts/eval/run.py` 属阶段 1）。
