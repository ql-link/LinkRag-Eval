# Track B · LLM 合成语料 — 细化设计

> **归档文档：仅供追溯，不是当前权威依据。** 替代关系见 [归档说明](../README.md)。

> 状态：设计稿（`.specs/rag-quality-eval/`，git-ignored）
> 上游：[phase1_5_golden_gen_design.md](phase1_5_golden_gen_design.md)（黄金集来源，Track B 在 §2.4）、[phase1_design.md](phase1_design.md)（GoldenSample schema）、[technical_design.md](technical_design.md)
> 范围：用 LLM 生成**真实格式文档**作评测语料，走真实 ingestion，产出带**可控 ground truth**的黄金集，零人工。
> 定位：补 Track A（开源纯文本）测不到的 **parser + chunker 全链路**；对通用 RAG，合成内容事实性不影响评测（见 §七）。
>
> ⚠️ **存储口径已更新（权威见 [eval_storage_design.md](eval_storage_design.md)）**：本文凡"走真实 ingestion /
> 在 `kb_document_chunk` 回定位 chunk_id"，一律改为经 **EvalIngestor（复用 core 组件、不走
> `ParseTaskPipeline`）灌进 `eval_corpus_chunk`**，`locate` 回定位目标为 **`eval_corpus_chunk`**，
> 留痕落 `eval_synth_fact`。分块/解析仍用与生产同一组件（口径不变）。

---

## 一、结论先行

Track B 的独特价值不在"又一批问答"，而在两点 Track A（开源数据集）给不了的能力：

1. **走通真实解析+分块链路。** 开源数据集是纯文本段落、绕过 parser；Track B 生成**真实格式文档**（PDF/DOCX/HTML/Markdown），经与生产完全一致的 解析→分块→索引 入库，**唯一能评 parser 各 provider 与 chunker 的 track**。
2. **Ground truth 由构造决定，无需人工标。** 文档由可标识的"事实单元（fact unit）"拼成，每个事实单元落到哪个 chunk 是**埋点 + 自动定位**出来的，不靠人审。问题针对某事实单元生成，`expected_chunk_ids` / `golden_answer` 由埋点直接确定——精确且零人工。

核心机制：**埋点（plant）→ 渲染真实格式 → 真实 ingestion → 按 distinctive 文本回定位 chunk_id → 据埋点反向生成 Q/A → 自动门禁。**

---

## 二、覆盖维度（对准项目实际 parser / chunker）

项目 parser 支持：`docx/doc`（WordParser）、`pdf`（PdfParser，后端 `mineru / opendataloader / naive`）、`html/htm`（HtmlParser）、`markdown`（入库源即 md）。Track B 须覆盖这些路径与结构边界：

| 维度 | 覆盖项 | 压测目标 |
| --- | --- | --- |
| 文件格式 | PDF / DOCX / HTML / Markdown | 各 parser provider |
| PDF 后端 | mineru / opendataloader / naive 各跑一份 | `PDF_PARSER_BACKEND` 三态、`PDF_PARSER_FALLBACKS` |
| 文档结构 | 多级标题、表格、有序/无序列表、长段落、代码块、图文混排 | chunker 边界与正文回填 |
| 文档长度 | 短（单 chunk）/ 中 / 长（跨多 chunk、跨段事实） | 分块切分、cross-chunk 问题 |
| 事实分布 | 事实集中单段 / 分散多段 / 需跨段综合 | 单跳 vs 多跳问题 |

> PDF 注意：born-digital PDF（md/html 渲染而来）测排版解析；若要测 OCR 路径，需图片型 PDF（可选，渲染为图像页），按需补。

---

## 三、可控 Ground Truth 的埋点机制（核心）

### 3.1 事实单元（fact unit）

文档不是自由生成，而是由一组**原子事实单元**组装。每个事实单元：

```python
@dataclass
class FactUnit:
    fact_id: str            # 唯一标识，仅用于内部追踪（不写进文档可见文本）
    statement: str          # 一句可问可答的事实，含一个 distinctive 短语（见 3.3）
    section_hint: str        # 该事实应落在文档哪一节（控制分布）
    answer: str             # 该事实对应的标准答案
```

LLM 生成时被要求：把这些事实单元自然地编织进文档对应章节，**保留每个 statement 的 distinctive 短语原文不改写**。

### 3.2 渲染 → 真实 ingestion → 回定位 chunk

```
fact units → LLM 编织成文档(md/结构) → 渲染为目标格式(PDF/DOCX/HTML) →
经真实 ingestion(解析→分块→索引) → 库内产生真实 chunk →
对每个 fact，按其 distinctive 短语在 chunk 正文里(归一化)匹配 → 命中的 chunk_id 即该 fact 的 expected_chunk_ids
```

**回定位用归一化匹配,不是裸 exact-match（B3）**:Track B 的存在理由就是测 PDF/mineru 等会改写/丢字/重排版的解析路径——裸 exact-match 会被一个全角/半角、空白、连字符差异打挂,且**解析越不保真,匹配失败率越高,使最该考验的场景贡献样本最少(幸存者偏差)**。故:
- 匹配分三档:**完全命中 / 归一化后命中（去空白·标点·全半角归一 + 高阈值相似度）/ 未命中**。前两档取该 chunk_id;多 chunk 命中(事实被切到边界)取全部。
- **未命中才是真·解析丢失**,丢弃并计数,且**按"格式 × PDF后端"分桶**报告。
- 注意:丢弃率混了"锚点没编织进去(compose 失败)"与"解析丢字"两类原因,**它是覆盖缺口指标,不是可归因的解析保真度指标**;对高丢弃率的格式/后端,诚实声明 Track B 在该路径上覆盖不足,而非假装覆盖。

### 3.3 distinctive 短语

每个 statement 内嵌一个低频、可检索的短语（带具体数字/专名/编号的子句），作为回定位锚点。要求 LLM 原样保留、不同义改写。锚点只为定位，不必显眼，自然融入即可。

### 3.4 反向生成 Q/A

对每个已定位的 fact：

- **问题**：据 `statement` 生成不含锚点原文的提问（避免问题=答案泄漏锚点），标注类型（单跳；跨段则组合多个 fact 生成多跳）。
- `expected_chunk_ids` = 该 fact 回定位到的 chunk(s)；`expected_doc_ids` = 文档 doc_id。
- `golden_answer` = `FactUnit.answer`。**因答案即埋入的事实、且确在上下文中，正确性/Context Recall 标签由构造保证可靠**（这点比开源抽取式答案更干净）。

### 3.5 换分块策略 → 自动重定位（B11，Track B 的隐藏优势）

换分块策略是高频回归场景,但它会使所有 chunk 粒度黄金集的 `expected_chunk_ids` 失效(phase1 `loader.precheck` 检出)。对**反向合成/开源**这意味着报废重做;但 Track B 因锚点持久化(`eval_synth_fact.anchor`,见 eval_storage §3.5),**换分块后无需重生成——对同一份冻结语料重跑分块,再用锚点重新匹配即可自动重建 `expected_chunk_ids`**。

```
换分块策略 → 同语料重分块 → 对每个 eval_synth_fact 按 anchor 重新(归一化)匹配新 chunk → 刷新 expected_chunk_ids
```

设计上把"换分块 → 自动重标"做成闭环(`golden/synth/relocate.py`),让可复现的代价从"报废重做"降到"重跑匹配",这是 Track B 相对其他来源的实质优势。

---

## 四、流水线与模块

```
src/evaluation/golden/synth/
├── spec.py          # 文档规格：格式 × 结构 × 长度 × 事实分布 的组合矩阵
├── facts.py         # 生成 fact units（含 distinctive 锚点）
├── compose.py       # 调 LLM 把 facts 编织成结构化文档（md/中间结构）
├── render.py        # 渲染为目标格式：md / html / docx(python-docx·pandoc) / pdf(weasyprint·pandoc)
├── ingest.py        # 经真实 ingestion 入评测租户（复用生产 parse→chunk→index）
├── locate.py        # 按 distinctive 锚点在 kb_document_chunk 回定位 chunk_id（精确匹配）
├── qa.py            # 据已定位 fact 反向生成 (query, golden_answer, type)
└── (复用) gen/gate.py  # 自动质量门禁（异模型可答性 + 召回回环 + 答案自洽）
```

流程：`spec → facts → compose → render → ingest → locate → qa → gate → GoldenSample(jsonl)`。

要点：

- **render 优先 born-digital**：md→html 直出；docx 用 `python-docx` 或 `pandoc`；pdf 用 `weasyprint`/`pandoc`。这些是 `[eval]` extra 里的可选渲染依赖，不入生产。
- **ingest 复用生产链路**：必须走真实 parse→chunk→index，否则失去 Track B 的意义（测 parser/chunker）。
- **locate 容错**：锚点匹配不到（解析丢字、被截断）→ 该 fact 丢弃并计数；命中多 chunk → 全取。丢弃率作为"解析保真度"的副产物指标。

---

## 五、覆盖矩阵驱动（spec.py）

按"格式 × PDF后端 × 结构 × 长度"组合成规格矩阵，每格生成若干文档，保证分层覆盖而非随机堆量。例：

```
PDF×mineru×表格密集×长文   →  N 篇
DOCX×多级标题×中           →  N 篇
HTML×图文混排×短           →  N 篇
MD×代码块×长×跨段事实       →  N 篇
...
```

矩阵让"哪种格式/结构下召回掉点"可归因到具体条件，呼应趋势看板的分组。

---

## 六、模型错配纪律（防双重合成偏置）

Track B 是"合成语料 + 合成问题 + 合成判官"，偏置风险最高。硬约束（记入快照）：

| 角色 | 模型 | 约束 |
| --- | --- | --- |
| 语料编织（compose） | 模型 A | 与下面尽量错开 |
| 问题/答案生成（qa） | 模型 B | ≠ A |
| 门禁复核（gate 可答性/自洽） | 模型 C | ≠ B，最好强于被测 |
| 评测判官（阶段 3） | 模型 D | ≠ 被测 CHAT，最好最强 |
| 被测系统 CHAT | 模型 E | 被评对象 |

`snapshot.validate_model_distinctness` 扩展校验这几个角色两两不同名。

---

## 七、对评测有效性的边界（诚实声明）

- **检索/重排评测：有效。** 只看"问题能否召回到埋了对应事实的 chunk"，与内容是否世界真相无关。
- **生成忠实度（Faithfulness）：有效但绝对分偏乐观（B5 同源偏置）。** 评的是"答案是否被上下文支持"，reference-free，与世界真相无关;但合成语料+合成问题+合成判官即便模型错开都是 LLM,反向合成的题"chunk 里写了答案"对 RAG 过于友好,Faithfulness 普遍虚高。**仅作相对追踪,绝对分不作权威。**
- **答案正确性 / Context Recall：有效且标签干净。** `golden_answer` = 埋入事实、确在上下文，构造即真值;**优先用此埋点真值而非 LLM 判官**,绕开同源偏置。
- **不代表真实业务分布。** 合成文档是 LLM 的"通用知识文档"想象，**不能当领域/业务权威**——但 LinkRag 为通用 RAG、无固定垂直，此局限可接受；若未来有真实文档再补最高保真来源。
- **数字按相对比较用**：跨配置回归方向可信,但"噪声恒定"前提在换 provider 时减弱,须经噪声地板校验(trend §5.0);绝对分数不作权威。

---

## 八、完成判据（Definition of Done）

1. `spec` 能产出覆盖 PDF（三后端）/DOCX/HTML/MD × 结构 × 长度的矩阵；每格可生成文档。
2. `render` 产出可被对应 parser 正确解析的真实格式文件；`ingest` 走生产链路入评测租户。
3. `locate` 按 distinctive 锚点在 `kb_document_chunk` **归一化匹配**回定位 chunk_id（完全/归一/未命中三档），多命中全取、未命中丢弃并**按格式×PDF后端分桶**计数（覆盖缺口指标，非保真度指标）。
3b. `relocate` 支持换分块后用锚点自动重建 `expected_chunk_ids`（B11 闭环）。
4. `qa` 产出 `expected_chunk_ids`/`expected_doc_ids`/`golden_answer` 由埋点确定的 `GoldenSample`，问题不泄漏锚点原文。
5. 复用 `gate` 自动门禁，全程无人工。
6. 五角色模型错配校验生效并记快照。
7. 两套口径（Track A 开源 / Track B 合成）分开汇报，均按相对比较使用。

---

## 九、本设计不做

- 不追求合成内容的领域/业务真实性（通用 RAG 不需要；检索/忠实度评测不依赖）。
- OCR/图片型 PDF 路径首版可选，按需补。
- 不引入人工环节。
- 不替代 Track A（开源通用回归基线）与未来真实文档来源。
