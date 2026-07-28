# 数据清洗质量检测模块 — 评测设计（md round-trip，零人工）

> **归档文档：仅供追溯，不是当前权威依据。** 替代关系见 [归档说明](../README.md)。

> 状态：设计稿（`.specs/rag-quality-eval/`，git-ignored）
> 上游：[framework_design.md](framework_design.md)（总架构）、[phase0_design.md](phase0_design.md)（Layer/contracts）、[phase1_5_trackB_llm_corpus_design.md](phase1_5_trackB_llm_corpus_design.md)（复用其 render 链路）、[technical_design.md](technical_design.md)
> 范围：作为质检模块中**独立的"数据清洗质量检测"子模块**，把 **数据清洗质量** 本身纳入评测点——链路最上游的一层。补足原 B9"该环节只能间接观测"的缺口。
> 术语：**数据清洗 = 把原始文档（Word/PDF/HTML）经 parser 转成结构化 md 的过程**。生产组件仍叫 `parser`（`IFileParser.parse`），本模块评的是它产出的"干净 md"质量。
> **边界**：本模块**只负责数据清洗质量，不负责分片（chunk）质量**。分片质量不在本模块范围（如需另议、单列模块）。
> 定位：与检索层一样**自成闭环、可独立交付、零人工**；不依赖召回栈，只需 parser + 标准 md 语料。

---

## 一、结论先行

LinkRag 的理想输入是**标准 md**，其余格式（Word/PDF/HTML）经 parser **清洗成 md** 再入库。**本模块的核心依据：清洗产出的 md 与原始标准 md 的一致性**——一致性越高，数据清洗质量越好。关键办法：**以标准 md 为参考做 round-trip**——

```
标准 md(参考真值) → 渲染成 DOCX/PDF/HTML → parser 清洗回 md(produced) → 比对 produced vs 参考 = 数据清洗质量
```

五条决策：

1. **数据清洗质量 reference-based、零人工。** 参考答案就是原始标准 md（"最理想输入"），无需人工标注。差距 = 清洗失真。**md 直输入是基准线（score≈1.0）**，Word/PDF/HTML 是被测路径。
2. **三大结构识别专项指标——标题、表格、图片**（清洗最易失真处）：
   - **标题（§4.3）**：(a) 是否识别到所有标题（完整率）；(b) 识别到的层级是否与原一致（层级一致率）。PDF 常无标题树元数据、靠版面推断，是重点。
   - **表格（§4.4）**：先检测清洗模式——① md 表格 ② 转图片 ③ 转 JSON，**三模式各有口径**（①③逐单元格/对应关系比，②比位置+完整度）；三者都先判位置正确。
   - **图片（§4.5）**：清洗后为 md 引用，重点判**上下文位置是否正确**（前驱/后继文本块锚点）+ 识别完整率。
3. **数据清洗时间是一等指标**：`parser.parse` 的墙钟耗时（单文档），逐 `(format, pdf_backend)` 报告，直接服务后端选型成本权衡。
4. **复用 Track B 的 render 链路，按 格式 × PDF 后端 分桶。** md→各格式渲染已在 Track B 实现；本模块在清洗步截一刀比对。PDF 三后端（mineru/opendataloader/naive）的标题/表格/图片识别 + 清洗时间单列对比，回答"换 PDF backend 值不值"。
5. **纯函数指标进 PR 门禁。** 比对逻辑不碰像素/IO，可单测；整轮 run（渲染+清洗）需活环境，属 integration。
6. **参考真值首选真实 md 数据集（见 §4.6）。** 采用 **`rojasdiego/chinese-markdown`**（18.7 万真实中文 md）作主参考源——md 本身即真值，零额外清洗、零循环、零合成偏置、结构真实；Track B 合成 md 降为"补结构边界"的辅助，OmniDocBench 真实 PDF+GT 作可选 Track 2。

依赖：只用 `core` 的 parser，零召回栈。

---

## 二、被依赖的生产接缝

| 用途 | 入口 | 说明 |
| --- | --- | --- |
| 数据清洗（解析） | `ParserFactory.get_parser(ext)` → `IFileParser.parse(source: Path) -> str` | 返回 **markdown 字符串**；`PdfParser`(后端 mineru/opendataloader/naive) / `WordParser` / `HtmlParser` |
| 渲染（复用 Track B） | `golden/synth/render.py` | md → DOCX(python-docx/pandoc) / PDF(weasyprint/pandoc) / HTML |

> PDF 后端三态由 `PDF_PARSER_BACKEND` / `PDF_PARSER_FALLBACKS` 控制，须进快照、分桶对比。

---

## 三、实现分两阶段、Layer 与模块

### 3.1 两阶段：数据集准备 → 质检（解耦，合理且推荐）

本模块**分两块实现**，第二块依赖第一块完成：

```
阶段一 · 数据集准备（一次性、可缓存）
  标准 md → 渲染成 DOCX/PDF/HTML → 存入 MinIO → 记对应关系表（md ↔ 各渲染件）
                                                  ↓ 冻结
阶段二 · 数据清洗质检（高频迭代，照表跑）
  照对应关系表取渲染件 → parser 清洗回 md → 与原 md 按指标比对 → CleaningQcReport
```

为什么这样拆（合理性）：

1. **渲染是重活、质检是高频活，解耦后质检迭代不重渲染。** 换 PDF backend / 改 parser 代码后回归，直接复用已冻结的渲染件。
2. **冻结渲染产物钉死渲染变量**，后续比不同 backend/parser 喂的是同一份输入，差异纯来自清洗器——比每次重渲染更干净地隔离清洗失真。
3. **对应关系表是可复现锚点**：质检照表取文件清洗、照表找参考 md 比对，run 间完全可复现；与"冻结评测语料"原则一致。
4. **职责清晰**：阶段一是数据工程，阶段二是纯评测，各自可测。
5. **约束**：渲染器/版本进表并冻结——换版本等于换输入，不与旧数据混比（同 provider 三态）。

### 3.2 Layer 与模块

phase0 `Layer` 枚举新增 `CLEANING`（在 RETRIEVAL 之前）：

```python
class Layer(str, Enum):
    CLEANING = "cleaning"  # 数据清洗质量（文档→md，md round-trip）
    RETRIEVAL = "retrieval"
    RERANK = "rerank"
    GENERATION = "generation"
    CORRECTNESS = "correctness"
```

```
src/evaluation/
├── golden/cleaning_dataset/        # 阶段一：数据集准备
│   ├── render.py                   #   md → DOCX/PDF/HTML（复用 Track B render）
│   ├── store.py                    #   渲染件存 MinIO（tolink-rag-eval/cleaning_corpus/）
│   └── registry.py                 #   写对应关系表 eval_cleaning_doc / eval_cleaning_rendered（见 eval_storage §3.6）
├── adapters/
│   └── cleaning_adapter.py         # 阶段二：照表取渲染件 → parser.parse → produced_md
└── metrics/
    └── cleaning.py                 # produced_md vs md_ref 比对（纯函数）
```

`StageOutput` 复用（phase0 §3.3）：清洗层把 `produced_md` / 结构化对照放 `raw`，指标读归一化对照结构。

> **阶段一产物落点**：渲染件存 MinIO `tolink-rag-eval/cleaning_corpus/<dataset>/<sample>.<fmt>`，原始 md 存 `.../<sample>.md`；对应关系进 eval schema 两张表（§3.6 引用 eval_storage）。阶段二照表读。

---

## 四、数据清洗质量适配器与指标

### 4.1 `cleaning_adapter.py`（Evaluable, layer=CLEANING）

阶段二照对应关系表取**已渲染件**（不现场渲染）：

```python
class CleaningEvaluable:
    layer = Layer.CLEANING
    def __init__(self, fmt: str, pdf_backend: str | None = None): ...
    async def run(self, rendered, *, upstream=None) -> StageOutput:
        # rendered 来自 eval_cleaning_rendered 行：含 object_key(渲染件) 与 doc 的 md_ref
        path = download(rendered.object_key)             # 从 MinIO 取冻结渲染件
        md_ref = load_md(rendered.doc.md_ref)            # 照表找参考 md
        parser = ParserFactory.get_parser(self.fmt)      # PDF 时按 backend
        t0 = perf_counter()
        produced_md = parser.parse(path)                 # 清洗；计入清洗时间
        return StageOutput(layer=Layer.CLEANING, query=rendered.doc.sample_id,
                           ranked=[], raw=CleaningPair(ref=md_ref, produced=produced_md),
                           elapsed_ms=int((perf_counter()-t0)*1000))
```

数据集来源：阶段一已渲染并入表的 `(md, format)` 组合（标准 md **首选真实 md 数据集 `rojasdiego/chinese-markdown`**，见 §4.6；Track B 合成补边界）。每行渲染件 × 每种 PDF backend 各跑一次。**md 直输入**作基准（produced=ref，分数上界）。

### 4.2 `metrics/cleaning.py`（纯函数，produced vs ref）

**核心依据：清洗产出的 md 与原始标准 md 的一致性。** 把两份 md 解析为块序列（heading/paragraph/table/list/image/code）后比对。归一化（去空白/标点/全半角）后计算：

| 指标 | 定义 | 抓什么 |
| --- | --- | --- |
| **文本完整性 / recall** | 参考文本 token 被 produced 保留的比例 | 丢字、漏段、漏页 |
| **文本噪声 / precision** | produced 中非参考的多余内容比例 | 乱码、页眉页脚、水印混入 |
| **标题识别完整率**（见 §4.3） | 原文标题被识别出来的比例（recall） | 标题漏识别（尤其 PDF） |
| **标题层级一致率**（见 §4.3） | 已识别标题中层级与原文一致的比例 | 层级识别错（h2 识成 h1/正文） |
| **标题顺序/文本一致** | 已识别标题的顺序与文本对齐率 | 标题错位/串行 |
| **表格识别**（见 §4.4，三模式） | 按清洗模式（md表/图片/JSON）分别评对应关系/完整度/位置 | 表格塌陷、错位、丢单元格、对应关系错 |
| **列表保真** | 列表项数 + 嵌套层级 | 列表还原 |
| **图片识别**（见 §4.5） | 图片 md 引用保留率 + **上下文位置正确率** | 图片丢失、错位、占位错误 |
| **顺序保真** | 块相对顺序一致性（序列对齐 / Kendall τ） | 段落乱序、跨栏错排 |
| **稳定性** | 同输入清洗 N 次输出一致率 | mineru/VLM 等非确定性后端 |
| **数据清洗时间** | 单文档 `parser.parse` 墙钟耗时 | 后端选型成本（一等指标） |

全部**逐 `(format, pdf_backend)` 分桶**。比对块序列的对齐用 LCS / 编辑距离 + 类型匹配；纯函数、可单测、进 PR 门禁（渲染产物可预先 fixture 化）。清洗时间由 `cleaning_adapter` 测量并落 `StageOutput.elapsed_ms`，进报告与台账。

### 4.3 标题识别评测（重点，分两种情况）

标题是 md 结构的骨架，且是**最易在清洗中丢失/错层**的部分——尤其 PDF：**很多 PDF 不提供标题树元数据（无 outline/bookmark），parser 只能靠版面线索（字号、加粗、编号、位置）识别哪些文本是标题、是几级标题**。因此标题识别成功与否必须单独度量，拆成两个正交指标：

设原文标题集 `H_ref = [(text_i, level_i)]`（顺序保留），produced 识别出的标题集 `H_prod`。先按文本（归一化）做对齐匹配 `H_ref ↔ H_prod`：

1. **标题识别完整率（recall）**：`|matched| / |H_ref|`。
   - 衡量"**是否识别到所有标题**"。漏识别（标题被当成正文）直接拉低此值。
   - 反向也记 **误识别率**：produced 中把正文/页眉误判为标题的数量 / `|H_prod|`（precision）。
2. **标题层级一致率**：在 `matched` 子集上，`|level 与原文相同| / |matched|`。
   - 衡量"**识别到的标题层级与原层级是否一致**"。如原文 h2 被识成 h1 或 h3 即层级错。
   - 可细分：层级**绝对一致**率（完全相等）与**相对结构一致**率（整体层级树同构、允许统一偏移，如全体 +1）。

> **PDF 标题识别专项**：因 PDF 无元数据标题树时全靠 parser 推断,标题指标对 PDF 后端(mineru/opendataloader/naive)差异最敏感,是"换 PDF backend"决策的关键信号。报告须把 PDF 三后端的标题识别完整率 + 层级一致率单列对比。对**有元数据标题树**的格式(如 DOCX 样式标题、HTML `<h1-6>`)作对照基线,凸显 PDF 推断的难度。

匹配口径:标题文本归一化后用相似度阈值匹配(防清洗微小改写导致漏配);一个原标题最多匹配一个 produced 标题;未匹配的原标题计入漏识别、未匹配的 produced 标题计入误识别。纯函数、可单测。

> **诚实边界**：渲染（md→PDF）本身也会影响标题呈现（如渲染器是否把 `#` 渲成够大的字号让 parser 认得出）,round-trip 测的是"渲染+清洗"联合标题保真。隔离办法:同一渲染产物比不同 backend(控制渲染变量);md→HTML→md(HTML 保留 `<h1-6>` 语义)作"标题识别上界"参照。

### 4.4 表格识别评测（重点，三种清洗模式各有口径）

参考真值是原始 md 表格，**结构化的单元格对应关系已知**（行 × 列 × 表头 × 单元格值）。但 parser 对同一张表可能产出**三种不同形态**，须先**检测模式**再按模式比对：

**模式检测**：在 produced md 中定位该表对应区域（按表上下文锚点 §4.5），判断它是 md 表格语法 / 图片引用 / JSON 代码块。先记一个 **表格模式分布**指标（各模式占比）——模式本身是重要信号：转图片丢失可检索性、转 md/JSON 保留结构。

| 清洗模式 | 适用指标 | 定义 |
| --- | --- | --- |
| **① md 表格** | **结构对应保真** | 行数/列数一致率；表头对齐；单元格按 (row, col) 对应的值匹配率；合并单元格还原。整体取**单元格对应 F1**（原表单元格集合 vs produced 单元格集合，按位置+内容匹配） |
| **② 转图片** | **位置正确 + 完整度** | (a) 图片在上下文位置正确（§4.5 同口径）；(b) **表格完整度**：图片是否完整覆盖原表（不截断/不漏行列）。内容无法逐格比，完整度用：图片存在 + 位置对 + 尺寸/区域 sanity；**可选** OCR 图片后比文本 recall 作完整度近似 |
| **③ 转 JSON** | **对应关系保真** | produced JSON 须与原表**同对应关系**：把 JSON 还原成 (row, col, value) 或 (表头→值) 三元组集合，与原表三元组做集合对齐，取 **对应 F1**；表头键名/层级一致；行列数一致 |

要点：

- **三模式都先要"位置正确"**：无论清洗成表/图/JSON，该表在文档中的相对位置必须对（用 §4.5 上下文锚点判定），位置错本身算缺陷。
- **模式②的内容完整度是弱信号**（像素无法逐格比），报告须诚实标注；若接入 OCR 则升为可比信号，但引入 OCR 依赖与其自身误差，列为可选。
- **模式①③可逐格比、是强信号**；JSON 的"对应关系"指：原表里"某行某列=某值""某表头下=某值"的对应,在 JSON 里必须能还原出同样的对应,而非仅文本包含。
- 全部**逐 `(format, pdf_backend)` 分桶**；纯函数（模式②的非 OCR 部分也是纯函数：存在/位置/区域）。

### 4.5 图片识别与上下文位置评测

清洗后图片以 **md 图片引用**（`![alt](path)`）形态出现。参考 md 里每张图片有确定的**上下文位置**（前驱/后继文本块）。指标：

| 指标 | 定义 | 抓什么 |
| --- | --- | --- |
| **图片识别完整率（recall）** | 原文图片被清洗出 md 引用的比例 | 图片丢失 |
| **图片误识别率** | produced 中多出的、原文没有的图片引用比例 | 把装饰/水印当图片 |
| **上下文位置正确率** | 每张匹配图片的**前驱/后继文本块**与参考一致的比例 | 图片插错位置、漂移到别处 |

**上下文位置怎么判**：在参考 md 里，每张图片记其锚点 = 紧邻的前一个文本块 + 后一个文本块（归一化）。在 produced md 里找到对应图片后，比较它的前后邻块是否匹配同一对参考锚点（允许清洗噪声、用相似度阈值）。匹配则"位置正确"。**表格转图片（模式②）复用同一套位置判定**。

> 图片匹配口径：图片本身像素难比，故按**位置锚点 + 数量 + （若有）alt 文本**匹配,而非比图像内容;一个原图最多匹配一个 produced 图。纯函数（不读像素）、可单测。

### 4.6 参考真值数据源（首选真实 md）

参考真值要"已知干净的标准 md"。优先级：

1. **真实 md 数据集（首选）·`rojasdiego/chinese-markdown`** —— 18.7 万真实中文 md 文件(来自 GitHub)。md 即真值,**直接渲染成各格式跑 Track 1**:无需"先清洗 PDF 才拿到参考"(那是循环、且正是被测对象)、无 LLM 合成成本与偏置、结构分布真实(真标题/表格/图文/嵌套)。授权:数据集含 per-item license 字段,**过滤出宽松许可(MIT/Apache/BSD 等)的文件用,保留署名**。
2. **Track B 合成 md（辅助·补边界）** —— 只补真实 md 覆盖不到的结构边界(特意构造的多模式表格、深层嵌套等)与需埋点的可控用例。
3. **OmniDocBench 真实 PDF + GT（可选 Track 2）** —— 测真实复杂/扫描 PDF(无渲染步、避免渲染失真);仅在要测真实世界 PDF 时引入,日常 md round-trip 不需要。

**一道必要的预处理（数据准备阶段，非被测清洗）**：真实 GitHub md 常混 YAML frontmatter、badges、内嵌 HTML、相对图片链接,需一道**轻量归一化/过滤**得到"干净标准 md"作参考(去 frontmatter/badge、规整图片引用、丢弃过短或非文档型 md)。这是一次性过滤,产出冻结后进 `eval_cleaning_doc`(`source='chinese-markdown'`)。

> 表格说明:真实 md 表格恒为 md 表语法,但仍能当**三种清洗模式**(md/图片/JSON)的参考——参考恒为 md 表,parser 输出何种形态由它自己决定,我们检测模式后比对(§4.4)。故真实 md 对表格专项也够用。

---

## 五、数据清洗质检结果模版（统一返回结构）

数据清洗质检跑完后，**按统一模版返回结果**，供报告渲染、持久化、回归对比共用。两级结构：单文档明细 + 跨样本聚合。

### 5.1 单文档明细 `CleaningQcItem`

一次"一个 md × 一种 `(format, backend)`"的质检结果：

```jsonc
{
  "sample_id": "doc-013",
  "format": "pdf",                      // pdf / docx / html / md
  "pdf_backend": "mineru",              // 仅 PDF；其余为 null
  "clean_ms": 1840,                     // 数据清洗时间（一等指标）
  "ok": true,                           // 清洗是否成功返回（异常/超时为 false）

  "text": { "completeness": 0.97, "noise": 0.02 },

  "heading": {                          // §4.3 标题识别（两情况）
    "recall": 0.92,                     // 是否识别到所有标题
    "false_rate": 0.05,                 // 误识别率
    "level_consistency_abs": 0.88,      // 层级绝对一致
    "level_consistency_rel": 0.95,      // 层级相对结构一致
    "missed": ["3.2 风险控制"]          // 漏识别清单（明细，便于排查）
  },

  "table": {                            // §4.4 三模式
    "mode_dist": { "md": 4, "image": 1, "json": 0 },  // 本文档各表的清洗模式
    "md_cell_f1": 0.94,
    "json_corr_f1": null,
    "image_position_ok": 1.0,
    "image_completeness": 0.90          // 弱信号（如启用 OCR）；否则 null
  },

  "image": {                            // §4.5
    "recall": 1.0, "false_rate": 0.0,
    "context_position_ok": 0.83,
    "misplaced": ["fig-2"]              // 位置错的图（明细）
  },

  "list_fidelity": 0.96,
  "order_fidelity": 0.99,
  "stability": 1.0,                     // 多次清洗一致率（非确定后端 <1）

  "artifacts": {                        // 见 §六 持久化
    "produced_md_ref": "runs/<run-id>/cleaning/doc-013.pdf.mineru.md",  // 可选
    "rendered_ref": "runs/<run-id>/render/doc-013.pdf"                  // 可选
  }
}
```

> 明细字段（`missed`/`misplaced`/`mode_dist`）是**排查用**，不进结构化台账，只随 per-sample 明细落对象存储（§六）。

### 5.2 跨样本聚合 `CleaningQcReport`

按 `(format, pdf_backend)` 分桶聚合，供报告与回归：

```jsonc
{
  "run_id": "20260613-1030-<sha>-pdf-backend-eval",
  "snapshot": { "pdf_backend": "mineru", "renderer": "weasyprint@x", "corpus": "synth-v1" },
  "buckets": [
    {
      "format": "pdf", "pdf_backend": "mineru", "n": 40,
      "metrics": {                       // 每项 = 桶内均值（+ 必要时 p95）
        "clean_ms_p50": 1720, "clean_ms_p95": 3010,
        "text_completeness": 0.96, "heading_recall": 0.90,
        "heading_level_consistency_rel": 0.94, "table_md_cell_f1": 0.93,
        "table_mode_image_ratio": 0.18, "image_context_position_ok": 0.81,
        "stability": 0.97
      }
    }
    // ... 其余 (format,backend) 桶
  ]
}
```

聚合层每个 metric 即一条 `eval_metric_result` 行（layer=cleaning，`format`/`backend` 进维度）。结果用历史规格中的专用 HTML 模版 `templates/cleaning_report_template.html` 渲染（该模版未迁入本仓库；沿用 eval_report_template 风格：自包含、涨绿跌红、口径脚注；分标题/表格/图片/清洗时间四区，逐 (格式×后端) 出表），`html_reporter` 注入 `CleaningQcReport` 数据。

> 该模版是 phase0 `models.py` 的具体化：`CleaningQcItem` 进 `StageOutput.raw` / per-sample 明细，`CleaningQcReport.buckets[*].metrics` 即 `MetricResult` 集合。指标计算只读归一化字段，明细 `missed`/`misplaced` 仅供人看。

---

## 六、清洗结果是否持久化（评估与策略）

区分三类"清洗结果"，各自持久化策略不同：

| 数据 | 是否持久化 | 落点 | 理由 |
| --- | --- | --- | --- |
| **聚合质检指标**（`CleaningQcReport.buckets`） | **持久化** | `eval_metric_result` 表（layer=cleaning） | 跨轮趋势/回归依赖；换 backend 对比的真相源 |
| **单文档明细**（`CleaningQcItem`，含 missed/misplaced/mode_dist） | **持久化（轻量）** | 对象存储 `runs/<run-id>/cleaning_detail.jsonl` | 排查"哪篇哪个标题漏了"用；体量小、按 run 存、不进 DB |
| **清洗产出物 produced_md / 渲染文件** | **默认不持久化，按条件留** | 对象存储 `runs/<run-id>/cleaning/*.md`（可选） | 见下 |

**produced_md 要不要存——关键看可复现性：**

- **确定性后端（docx/html/naive 等）**：produced_md 可由 `md_ref + render + parse` 重放，**默认不存**（省空间），需要时重跑即可。
- **非确定性后端（mineru/VLM）**：同输入多次清洗输出可能不同（正是 `stability` 指标抓的），**那一轮的确切输出不可重现**——若要事后审计"mineru 这轮到底输出了什么导致掉分"，必须当场存。策略：**非确定后端 + 该样本质检不达标（或 stability<1）时落 produced_md**，其余不存。
- **渲染文件**：体量大、可由 md_ref 重放，**默认不存**；仅在 round-trip 异常需复盘时临时留。

**保留期**：`cleaning_detail.jsonl` 与按条件留存的 produced_md 设对象生命周期（如 N 天/保留最近若干 run），台账指标不过期。无 DB 环境时，聚合指标随 `result.json`、明细随 `cleaning_detail.jsonl` 一并落 `.specs`（ResultStore 文件后端）。

**一句话**：**指标必须持久化（进表，为趋势）；明细轻量持久化（排查）；清洗产出物默认不存、仅在不可复现（非确定后端）或异常时按条件留。**

---

## 七、与其他评测点的关系

- **上游独立**：数据清洗评测不需召回/重排/生成栈，**可在 M1 并行甚至更早交付**（只要 parser + md 语料就绪）。
- **与 Track B 共享语料与 render**：Track B 的 md 既是检索/生成语料、又是数据清洗质量参考；render.py 共用。
- **与检索层互补**：清洗评"入库前的内容保真"，检索评"入库后的召回排序"。换 PDF backend 时，清洗指标给"内容保真变化"、检索指标给"对召回的传导影响"，两者联看可归因。
- **Track B 锚点丢弃率**之前被当作间接信号——现在数据清洗质量有**直接指标**，锚点丢弃率退为辅助。

---

## 八、运行与产物

- **执行**：`scripts/eval/run.py --layers cleaning --run-id <id>`。渲染+清洗需活环境（pandoc/weasyprint/mineru 等），属 integration；指标数学单测进 PR 门禁。
- **快照**：记录 `PDF_PARSER_BACKEND` / fallbacks、渲染器版本、md 语料版本。
- **产物**：指标进 `eval_metric_result`（layer=cleaning，新增 `format`/`backend` 维度或并入 config）；HTML 报告按 `(format, backend)` 分桶出表（用 cleaning_report_template）。
- **回归判据**：同 technical_design §七 统一口径——超噪声地板 + 最小样本量；换 backend 属配置变更，同口径回归。

---

## 九、完成判据（Definition of Done）

1. `Layer` 增 `CLEANING`；`cleaning_adapter` 落地，复用 Track B render 与生产 `ParserFactory`；核心比对依据为 **produced_md vs 原始标准 md 的一致性**。
2. `metrics/cleaning.py` 产出文本完整性/噪声/表格/列表/图片/顺序/稳定性 + **数据清洗时间**，**逐 `(format, pdf_backend)` 分桶**，纯函数进 PR 门禁。
3. **标题识别专项（§4.3）**：产出 (a) **标题识别完整率**（是否识别到所有标题）+ 误识别率、(b) **标题层级一致率**（识别到的层级是否与原一致，含绝对/相对结构两口径）；PDF 三后端单列对比，DOCX/HTML 有元数据标题树作对照基线。
4. **表格识别专项（§4.4）**：先**检测清洗模式**（md表/图片/JSON）并报模式分布；按模式评——① md 表格→单元格对应 F1；② 转图片→上下文位置 + 完整度（OCR 可选）；③ 转 JSON→对应关系 F1。三模式都先判位置正确。
5. **图片识别专项（§4.5）**：产出图片识别完整率/误识别率 + **上下文位置正确率**（前驱/后继文本块锚点匹配）；表格转图片复用同一位置判定。
6. **数据清洗时间**与各质量指标进 `eval_metric_result` 并在 HTML 报告分桶呈现；换 PDF backend 可同口径回归对比。
7. **统一结果模版（§五）**：质检完按 `CleaningQcItem`（单文档明细）+ `CleaningQcReport`（分桶聚合）返回；聚合 metric 映射到 `eval_metric_result`，明细字段供报告/排查。
8. **持久化策略（§六）**：聚合指标进表（趋势）；单文档明细落对象存储 `cleaning_detail.jsonl`；produced_md 默认不存，仅非确定后端/异常按条件留。
9. md 直输入作基准线；md→HTML→md 作清洗/标题识别能力上界参照；渲染失真在报告中标注（round-trip 联合保真）。
10. **参考真值数据源（§4.6）**：首选真实 md 数据集 `rojasdiego/chinese-markdown`（过滤宽松许可 + 一道归一化得干净标准 md，入 `eval_cleaning_doc` 标 `source='chinese-markdown'`）；Track B 合成补边界；OmniDocBench 可选 Track 2。
11. 与 Track B 共享 render 链路，零人工。

---

## 十、本设计不做

- **不做分片（chunk）质量** —— 本模块只评数据清洗；分片质量另议、不在此范围。
- 不评 md 直输入的"内容质量"（那是用户输入，不在系统可控范围）。
- 不追求把渲染失真与清洗失真完全解耦（用控制变量法近似，诚实标注 round-trip 联合口径）。
- 不引入人工标注（参考即标准 md，构造即真值）。
