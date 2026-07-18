# Golden V2 真实召回评测改造方案

> 状态:实施中,核心链路已落地
> 适用范围:检索层黄金集、召回指标、调参/验收数据拆分。
> 上游:当前 `phase1_5_golden_gen_design.md` 是历史方案,其中"开源数据集 doc 粒度主力"不再作为主评测口径。本文覆盖黄金集 v2 的当前目标态。

## 一、结论

当前 `recall@10 > 0.90` 的主要问题不是单一算法太强,而是评测集口径偏宽:样本规模小、query 偏短、doc 粒度标注多、合成问题从目标 chunk 反推。v2 改造目标是把黄金集拆成三套,并把主指标收紧到 chunk 粒度:

| 集合 | 作用 | 是否用于 headline | 主要来源 |
| --- | --- | --- | --- |
| Regression Set | 防回归,保证历史可比 | 否,只做稳定性基线 | 现有 clean golden + 历史报告绑定样本 |
| Realistic Set | 主评测,代表真实用户问题 | 是 | 真实 query/客服问题/开源真实 query/少量非泄漏改写 |
| Hard Set | 难例,暴露系统短板 | 单列,不混入主均值 | 干扰文档、多约束、多 chunk、同义/缩写/数字条件等 |

硬规则:

1. 主指标优先 `expected_chunk_ids`;纯 `expected_doc_ids` 只进 doc 诊断口径。
2. chunk 粒度和 doc 粒度分开报,不得混成一个 `recall@10`。
3. 不用当前被测召回链路筛掉题目;召不回但相关的样本必须保留为 hard case。
4. 标注池由多路候选组成:当前 dense、BM25、另一个 embedding、随机近邻。
5. 调参集和盲测集拆开,默认 70% tune / 30% blind。
6. 新测评语料、chunk、query 种子、难例草稿不得使用项目 `.env.eval` 中配置的业务/评测模型生成;统一由 Codex sub-agent 指定 `gpt-5.3-codex-spark` 离线批量预生成,再批量导入 eval 流程。
7. 语料规模按阶段扩容:pilot 先跑 1k-5k chunk 验证链路,medium 扩到约 2w chunk 调参,正式背景库目标 10w chunk;10w 是背景语料规模,不是 golden query 规模。

规模建议:

| 阶段 | 背景语料 | Query 规模 | 目标 |
| --- | ---: | ---: | --- |
| Pilot | 1k-5k chunk | 100-300 seeds | 验证 Spark bundle、ingest、BM25、候选池、标注闭环 |
| Medium | 2w chunk | 500-1000 seeds | 观察大语料干扰下的 recall 变化,调 fusion/topK/BM25 权重 |
| Realistic Scale | 10w chunk | realistic blind 500-1000 + hard blind 200-500 | 作为正式背景库做主报告,headline 只看 blind + chunk |

10w 语料库只用于提高搜索空间和相似干扰强度。真实度仍由 query 来源、chunk 级 qrel、多路候选池和 blind eval 决定;不能用 10w 合成语料替代真实 query。

## 二、模块总览

```
golden_v2/
├── sources/              # query 种子来源:日志、客服、开源、非泄漏改写
├── spark_pregen/         # GPT-5.3-Codex-Spark 离线预生成语料/query/难例草稿
├── candidates/           # 独立候选池:dense / bm25 / alt embedding / random
├── labeling/             # DeepSeek 判相关性 + 证据 chunk 选择
├── split/                # regression / realistic / hard + tune/blind 拆分
├── metrics/              # chunk/doc 分名指标与报告口径
├── storage/              # eval_query/eval_qrel/jsonl manifest
└── cli/                  # 构建、诊断、导出、跑分命令
```

本文按模块定义输入、输出、规则和验收。

## 三、Spark 离线预生成模块

### 3.1 定位

`spark_pregen` 用于提前批量生成可导入 eval 的测评语料草稿、预切 chunk、query 种子、难例设计和改写候选。它不是最终判官,也不直接决定 `expected_chunk_ids`。最终 golden 仍必须经过候选池召回、DeepSeek 逐 chunk 标注、QC 和 tune/blind 拆分。

核心边界:

- 生成模型固定为 Codex sub-agent 的 `gpt-5.3-codex-spark`。
- 不读取、不使用 `.env.eval` 中的 `EVAL_JUDGE_MODEL`、`EVAL_EMBED_MODEL`、`EVAL_SPARSE_MODEL`。
- 不调用项目运行时 LLM 客户端生成数据。
- 不打印、不读取任何 API key。
- 预生成产物只作为"原料",不能跳过后续标注池和 DeepSeek 判定。
- `.env.eval` 仅服务 eval 自身运行,不得承载 Spark 离线生成流程的凭据或模型配置。

### 3.2 为什么不用项目配置模型

项目配置模型属于被测或评测链路的一部分。如果用同一批模型反向生成 query、再用同一链路评测,会形成同源偏置:题目更贴合当前模型擅长的表达方式,召回率会继续偏乐观。Spark sub-agent 的作用是把"造数据"从项目运行配置中剥离出来,让数据准备成为离线、可审计、可批量复现的前置阶段。

### 3.3 预生成产物

建议输出目录:

```
runs/golden_v2/spark_pregen/
├── bundle_manifest.json         # 可重放 bundle 元数据、生成模型、文件 hash
├── corpus_blueprints.jsonl      # 待导入语料草稿,不是最终 chunk
├── chunk_records.jsonl          # 可选:已预切的 chunk 原料,导入时仍需重算/校验 id
├── query_seeds.jsonl            # 真实风格 query 种子
├── hard_case_seeds.jsonl        # 难例草稿
├── rewrite_seeds.jsonl          # 非泄漏改写候选
└── spark_pregen_report.md       # 数量、类型、领域、风险统计
```

`bundle_manifest.json`:

```json
{
  "schema_version": "eval-offline-batch-v1",
  "batch_id": "batch-20260708-a1",
  "generator": {
    "provider": "codex-subagent",
    "model": "gpt-5.3-codex-spark",
    "prompt_hash": "sha256:...",
    "temperature": 0.2
  },
  "source_ref": {
    "doc_scope": "eval_kb_frozen_v3",
    "seed_version": "seedset-20260707"
  },
  "artifacts": [
    {"kind": "corpus_blueprints", "path": "corpus_blueprints.jsonl", "sha256": "..."},
    {"kind": "chunk_records", "path": "chunk_records.jsonl", "sha256": "..."},
    {"kind": "query_seeds", "path": "query_seeds.jsonl", "sha256": "..."},
    {"kind": "hard_case_seeds", "path": "hard_case_seeds.jsonl", "sha256": "..."}
  ],
  "created_at": "2026-07-08T00:00:00Z",
  "created_by": "codex-subagent"
}
```

`corpus_blueprints.jsonl`:

```json
{
  "blueprint_id": "spark-corpus-0001",
  "domain": "policy",
  "genre": "faq|manual|notice|product|medical|ecom",
  "title": "文档标题",
  "body": "拟导入评测语料的正文草稿",
  "facts": [
    {"fact_id": "f1", "statement": "可验证事实", "answer": "答案短语"}
  ],
  "risk_tags": ["synthetic", "needs_ingest"]
}
```

`chunk_records.jsonl`:

```json
{
  "dataset_id": 990201,
  "doc_id": 12003,
  "source_passage_id": "spark-corpus-0001-p03",
  "ordinal": 3,
  "content": "拟导入评测语料的 chunk 正文",
  "content_hash": "sha256:...",
  "chunk_id": "可选;如给出,导入时必须与 uuid5 规则一致",
  "metadata": {"batch_id": "batch-20260708-a1"}
}
```

`query_seeds.jsonl`:

```json
{
  "seed_id": "spark-query-0001",
  "query": "用户自然问法",
  "source": "spark_pregen",
  "domain": "policy",
  "type_hint": "keyword|paraphrase|longtail|multi_constraint|cross_chunk",
  "must_not_contain": ["禁止直接泄漏的答案词"],
  "metadata": {"blueprint_id": "spark-corpus-0001"}
}
```

`hard_case_seeds.jsonl`:

```json
{
  "seed_id": "spark-hard-0001",
  "query": "难例问题",
  "hard_reason": "no_keyword|similar_docs|multi_constraint|alias|number_time|cross_chunk",
  "distractor_plan": "需要构造哪些相似但错误的干扰文档",
  "domain": "policy",
  "metadata": {}
}
```

### 3.4 生成批次建议

首批可以预生成较大原料池,再由后续流程筛选:

| 产物 | 建议数量 | 进入最终集前处理 |
| --- | ---: | --- |
| corpus blueprints | 500-1000 | 导入 eval 语料、切 chunk、建索引 |
| query seeds | 2000-5000 | 候选池召回 + DeepSeek 标注 |
| hard case seeds | 500-1000 | 保留 hard reason,标注后进 Hard Set |
| rewrite seeds | 500-1000 | 去重、泄漏检测、候选池标注 |

批量预生成时宁可多产原料,不要直接扩大最终 golden。最终 golden 必须按 §十三验收标准筛出小而可信的 blind/tune 集。

### 3.5 导入流程

1. Spark sub-agent 离线生成 `spark_pregen/*.jsonl`。
2. 导入器校验 `bundle_manifest.json`、文件 hash、schema version 和 `generator.model`。
3. `corpus_blueprints` / `chunk_records` 转成 collection/manifest 或自有导入格式。
4. 通过 `linkrag-eval ingest` 导入 eval MySQL + Qdrant dense/sparse。
5. 通过 `linkrag-eval bm25-backfill` 重建 SQLite FTS5 BM25。
6. `query_seeds` 和 `hard_case_seeds` 进入候选池模块。
7. 候选池由 dense/BM25/alt/random 生成 topN。
8. DeepSeek 逐候选 chunk 判相关性。
9. 构建 Regression / Realistic / Hard,并拆 tune/blind。

### 3.6 质量约束

- Spark 生成的 query 不得直接包含答案原文或长片段原文。
- Spark 只能提供 `type_hint` / `hard_reason` / `distractor_plan`,不能写最终 `expected_chunk_ids`。
- 所有 query 必须去重;同义改写需绑定同一 `canonical_query_id`。
- 生成语料必须能通过 eval ingest,不能直接写 `eval_corpus_chunk` 绕过索引。
- hard case 必须保留失败价值,当前召回 miss 不得作为丢弃理由。

### 3.7 风险

| 风险 | 影响 | 处理 |
| --- | --- | --- |
| Spark 合成风格单一 | realistic set 仍不真实 | 混入真实日志/客服/开源 query;报告展示 source 分布 |
| Spark 泄漏答案词 | 召回虚高 | `must_not_contain` + ngram 泄漏检测 + DeepSeek 复核 |
| 预生成量过大导致低质样本混入 | 标注成本上升 | 候选池前先做去重、长度、模板化过滤 |
| Spark 直接标 reference | 循环偏差 | 禁止 Spark 写最终 qrel;reference 只由候选池 + DeepSeek 判定生成 |
| 离线生成模型与项目模型混用 | 结果不可解释,召回率偏乐观 | manifest 强制 `gpt-5.3-codex-spark`;导入器拒绝 `.env.eval` generator 字段 |

## 四、数据集分层模块

### 4.1 Regression Set

定位:历史回归尺,不是能力证明。允许保持偏易,但必须在报告中标记为 `dataset_role=regression`。

来源:

- 现有四域 clean golden。
- 历史报告绑定的稳定样本。
- 过去线上 bug 的复现样本。

规则:

- 保留原 `query`、`expected_doc_ids`、历史 `run_id` 绑定关系。
- 若能映射到 chunk,补 `expected_chunk_ids`;不能映射的保留 doc 诊断口径。
- 不参与新 provider 的最终能力宣称。

验收:

- 固定样本 id 不变。
- 支持一键跑历史基线。
- 报告 headline 不默认展示 regression set 分数。

### 4.2 Realistic Set

定位:主评测集合,尽量贴近真实用户问题。

来源优先级:

1. 线上搜索/问答日志脱敏抽样。
2. 客服、运营、业务侧真实问题。
3. 开源真实检索 query。
4. 少量 LLM 改写,但只能从 query 种子改写,不能从目标 chunk 直接反推。

采样要求:

- query 长度分桶:短 query、中等自然问句、长多约束问句均要覆盖。
- 类型分桶:关键词、改写、长尾细节、多约束、跨段落。
- 领域分桶:按 `eval_dataset.domain` 保证每域样本数可见。
- 每条 query 必须经过候选池标注生成 `expected_chunk_ids`。

验收:

- `expected_chunk_ids` 覆盖率 >= 95%。
- doc-only 样本不得进入主评测 headline。
- query 中位长度、p90 长度写入构建报告。

### 4.3 Hard Set

定位:难例集合,用于发现短板,不与主集静默混算。

难例类型:

- 同领域相似文档干扰。
- 问法不含答案关键词。
- 多约束查询,例如时间 + 对象 + 条件。
- 多 chunk / 跨段落问题。
- 别名、缩写、同义表达。
- 数字、时间、政策条件类问题。
- 正确答案与多个错误候选高度相似。
- 当前系统 topK 未召回,但独立标注认为相关。

规则:

- hard case 允许当前系统召不回。
- 召不回不是丢弃理由,而是进入 `hard_reason=current_miss`。
- 报告单列 `hard_recall_chunk@k`,不并入 realistic headline。

验收:

- 每条 hard case 必须有 `hard_reason`。
- hard set 至少覆盖 5 类难例。
- 每类样本量低于 15 时报告标记"仅定性"。

## 五、Query 种子模块

### 5.1 输入

统一输入结构:

```json
{
  "seed_id": "log-20260708-0001",
  "query": "用户原始问题或脱敏后问题",
  "source": "log|support|opensource|rewrite",
  "domain": "medical|ecom|video|policy|unknown",
  "ts": "2026-07-08",
  "metadata": {}
}
```

### 5.2 脱敏与过滤

必须过滤:

- 手机号、邮箱、身份证、地址、订单号等个人信息。
- 明确无法从评测语料回答的问题。
- 过短无意义 query,例如单字、纯符号。
- 重复 query。

输出:

- `query_seeds.jsonl`
- `query_seed_report.md`:来源分布、长度分布、过滤原因统计。

## 六、候选池模块

### 6.1 目标

构造与被测系统相对独立的标注池,避免"只标当前系统召回到的内容"造成循环论证。

### 6.2 候选来源

每条 query 取候选池:

| 来源 | topN | 说明 |
| --- | ---: | --- |
| current_dense | 50 | 当前系统 dense,用于覆盖现有能力 |
| bm25_sqlite_fts5 | 50 | SQLite FTS5 BM25,词法召回 |
| alt_embedding | 50 | 另一个 embedding 模型或固定开源 embedding |
| random_neighbor | 20 | 同 dataset 随机 chunk,估计误标与判官偏差 |
| qrel_seed_doc | 可选 | 如果 query 来自开源 qrel,加入原始正例 doc 的 chunk |

合并去重后形成 `candidate_pool`。

实现分两档:

- Pilot 文件模式:`golden-v2 candidate-pool --seeds --chunks` 使用 `bm25_local + random_neighbor`,用于验证 schema、去重、报告与后续标注闭环。
- 活栈模式:`golden-v2 candidate-pool-live --seeds --dataset-ids` 从 eval MySQL 取 chunk 正文,调用被测召回链路分别获取 `current_dense`、`bm25_sqlite_fts5`、`current_sparse` 分路候选;如配置 `EVAL_ALT_EMBED_*` 并启用 `--sources alt_embedding`,会用独立 embedding 对 eval chunk 做本地 cosine 扫描;最后再加入 `random_neighbor`。它使用同一输出 schema,可直接进入 DeepSeek 标注。
  - 候选池分路阈值与正式评测阈值解耦,默认 `--dense-score-threshold 0.0 --sparse-score-threshold 0.0`,目的是扩大标注池而不是模拟线上排序。`alt_embedding` 默认不设分数阈值,只按 `--route-top-n` 取 topN;若要在 pilot 计划中显式记录"不实质过滤",使用 `--alt-score-threshold -1.0`。
  - 正式评测阈值仍走运行时配置:代码默认 dense `0.20`、sparse `0.40`;当前本地 `.env.eval` 已覆盖为 dense `0.30`、sparse `0.40`。报告解读时必须记录实际 snapshot,不能只看代码默认值。
  - 2026-07-09 pilot 发现 Ark sparse 在 `dataset_id=990901` 上 top 分数约 `0.15-0.17`;沿用正式评测的 `EVAL_RECALL_SPARSE_SCORE_THRESHOLD=0.40` 会导致 sparse 分路稳定 0 命中。
- `alt_embedding` 必须与当前 `EVAL_EMBED_MODEL` 不同源;它只用于候选池,不写正式 Qdrant,不参与被测系统主评测。
- `alt_embedding` 向量缓存写入 `EVAL_ALT_EMBED_SQLITE_PATH`。缓存 key 为 `chunk_id + alt 模型指纹 + content_hash`,语料变更后会自动重算 stale chunk。

### 6.3 关键纪律

- 当前被测召回只能是候选来源之一,不能作为通过/丢弃门禁。
- alt embedding 必须与当前 dense 模型不同。
- random candidates 必须保留在 DeepSeek 判定池中,用于估计 false positive。
- 若当前系统未命中但 alt/BM25/判官命中,样本进入 Hard Set,不得丢弃。

输出:

```json
{
  "query_id": "real-0001",
  "candidates": [
    {
      "chunk_id": "...",
      "doc_id": 123,
      "dataset_id": 990201,
      "sources": ["bm25", "alt_embedding"],
      "rank_by_source": {"bm25": 3, "alt_embedding": 17}
    }
  ]
}
```

## 七、DeepSeek 标注模块

### 7.1 判定任务

对每个 `(query, candidate_chunk)` 做二元或分级判定:

- `relevant=true`:chunk 可直接回答或提供关键证据。
- `relevant=false`:chunk 不能回答,即使同 doc 也不算。
- 可选 `grade=0..3`:用于 NDCG 分级口径。

### 7.2 Prompt 纪律

判官只看 query 和候选 chunk,不看检索来源和 rank。输出 JSON:

```json
{
  "relevant": true,
  "grade": 2,
  "evidence_span": "支持判断的原文片段",
  "reason": "为什么相关或不相关"
}
```

### 7.3 质量控制

- 每条 query 至少保留 1 个 relevant chunk,否则进入 `unresolved` 不进主集。
- random candidates 的相关率异常高时,标记判官偏宽,本轮作废或重跑。
- 对高风险样本做双判官复核:DeepSeek + 另一个模型。
- 判定结果缓存为 jsonl,支持续跑,不重复花费。

输出:

- `judgments.jsonl`
- `judge_qc_report.json/md`:相关率、random relevant rate、无正例样本数、来源覆盖、门禁 failures/warnings。

已实现入口:

```bash
linkrag-eval golden-v2 qc \
  --judgments runs/golden_v2/judgments/deepseek_judgments.jsonl \
  --report-out runs/golden_v2/judgments/deepseek_judgments_qc.json \
  --markdown-out runs/golden_v2/judgments/deepseek_judgments_qc.md \
  --max-random-relevant-rate 0.05 \
  --max-unresolved-rate 0.30

linkrag-eval golden-v2 review-queue \
  --judgments runs/golden_v2/judgments/deepseek_judgments.jsonl \
  --out runs/golden_v2/judgments/deepseek_judgments_review_queue.jsonl \
  --report-out runs/golden_v2/judgments/deepseek_judgments_review_queue_report.json

linkrag-eval golden-v2 review-label \
  --review-queue runs/golden_v2/judgments/deepseek_judgments_review_queue.jsonl \
  --candidate-pool runs/golden_v2/candidates/candidate_pool.jsonl \
  --out runs/golden_v2/judgments/review_judgments.jsonl \
  --report-out runs/golden_v2/judgments/review_judgments_report.json \
  --reviewer-model another-judge-model

linkrag-eval golden-v2 adjudicate \
  --judgments runs/golden_v2/judgments/deepseek_judgments.jsonl \
  --reviews runs/golden_v2/judgments/review_judgments.jsonl \
  --out runs/golden_v2/judgments/adjudicated_judgments.jsonl \
  --report-out runs/golden_v2/judgments/adjudication_report.json \
  --policy manual_on_conflict \
  --conflict-out runs/golden_v2/judgments/manual_conflicts.jsonl
```

## 八、黄金集构建模块

### 8.1 GoldenSample 规则

主样本必须写:

```json
{
  "id": "real-0001",
  "query": "...",
  "dataset_ids": [990201],
  "expected_chunk_ids": ["..."],
  "expected_doc_ids": [123],
  "type": "paraphrase",
  "note": "role=realistic; source=log; split=blind"
}
```

规则:

- `expected_chunk_ids` 是主 reference。
- `expected_doc_ids` 仅用于诊断和回溯。
- 纯 doc-only 样本只能进 `regression_doc_only` 或诊断集。
- 每条样本标注 `role`: `regression|realistic|hard`。
- 每条样本标注 `split`: `tune|blind`。

### 8.2 Tune / Blind 拆分

默认:

- 70% tune:用于阈值、topK、fusion weight 调参。
- 30% blind:用于最终报告和验收。

拆分方式:

- 按 query hash 确定性拆分。
- 同一 query 的改写样本必须落同一 split,防泄漏。
- 同一 source doc 的高度相似 query 尽量落同一 split。

验收:

- 调参命令只能默认读取 tune。
- 标准验收命令默认读取 blind。
- 报告同时输出 tune/blind,但 headline 用 blind。

## 九、指标与报告模块

### 9.1 指标命名

必须分名:

| 粒度 | 指标名 |
| --- | --- |
| chunk | `recall_chunk@k`, `hit_rate_chunk@k`, `mrr_chunk`, `map_chunk`, `ndcg_binary_chunk@k` |
| doc | `recall_doc@k`, `hit_rate_doc@k`, `mrr_doc`, `map_doc`, `ndcg_binary_doc@k` |

禁止再输出混合 `recall@10` 作为 headline。

### 9.2 Headline 规则

报告 headline 优先级:

1. `realistic + blind + chunk`
2. `hard + blind + chunk` 单列
3. `regression + chunk/doc` 只在回归区展示

### 9.3 报告必须展示

- query 来源分布。
- query 长度分布。
- role 分布:regression / realistic / hard。
- split 分布:tune / blind。
- chunk/doc 指标分开表。
- hard case 类型分桶。
- 当前系统 missed 但判官认为相关的样本列表。

## 十、存储模块

### 10.1 文件产物

建议目录:

```
runs/golden_v2/
├── spark_pregen/bundle_manifest.json
├── spark_pregen/corpus_blueprints.jsonl
├── spark_pregen/chunk_records.jsonl
├── corpus/collection.tsv
├── corpus/manifest.jsonl
├── seeds/query_seeds.jsonl
├── candidates/candidate_pool.jsonl
├── judgments/deepseek_judgments.jsonl
├── golden/regression.jsonl
├── golden/realistic_tune.jsonl
├── golden/realistic_blind.jsonl
├── golden/hard_tune.jsonl
├── golden/hard_blind.jsonl
└── reports/build_report.md
```

### 10.2 MySQL 映射

已有表可继续承载:

- `eval_query`:query、dataset scope、golden answer、note。
- `eval_qrel`:chunk/doc reference 与 grade。
- `eval_run`:snapshot 记录 role/split/filter。
- `eval_metric_result`:存分名后的指标。

建议在 `note` 或 `snapshot_json` 中先记录:

```json
{
  "dataset_role": "realistic",
  "split": "blind",
  "reference_granularity": "chunk",
  "generator_model": "gpt-5.3-codex-spark",
  "generator_batch_id": "batch-20260708-a1",
  "judge_model": "deepseek-v4-flash",
  "candidate_sources": ["dense", "bm25_sqlite_fts5", "alt_embedding", "random"]
}
```

后续如查询压力变大,再考虑给 `eval_query` 增加结构化字段。

## 十一、CLI 模块

建议新增命令:

```bash
# -1. 生成 2w/10w 分批扩容计划与成本估算(只写本地计划,不连活栈)
linkrag-eval golden-v2 scale-plan \
  --stage scale_100k \
  --target-chunks 100000 \
  --dataset-id-start 991000 \
  --batch-chunks 5000 \
  --query-seed-target 1000 \
  --out-dir runs/golden_v2/scale_100k_plan

# 0. 导入 Spark 离线预生成 bundle
linkrag-eval golden-v2 spark-import \
  --bundle runs/golden_v2/spark_pregen/bundle_manifest.json \
  --out runs/golden_v2/seeds/query_seeds.jsonl

# 1. 将 Spark chunk_records 导出现有 ingest 输入格式
linkrag-eval golden-v2 spark-corpus-export \
  --chunks runs/golden_v2/seeds/chunk_records.jsonl \
  --collection runs/golden_v2/corpus/collection.tsv \
  --manifest runs/golden_v2/corpus/manifest.jsonl \
  --dataset-id 990901

# 2. 导入/清洗真实 query 种子
linkrag-eval golden-v2 seed-import \
  --source log \
  --input data/raw_queries.jsonl \
  --out runs/golden_v2/seeds/query_seeds.jsonl \
  --id-field qid \
  --query-field query \
  --report-out runs/golden_v2/seeds/seed_import_report.json

# 2.5 生成 pilot 全流程计划和本地预检命令
linkrag-eval golden-v2 pilot-plan \
  --raw-query-input data/raw_queries.jsonl \
  --source log \
  --dataset-ids 990901 \
  --reviewer-model another-judge-model \
  --out-dir runs/golden_v2/pilot_plan

linkrag-eval golden-v2 pilot-preflight \
  --seeds runs/golden_v2/seeds/query_seeds.jsonl \
  --dataset-ids 990901 \
  --reviewer-model another-judge-model \
  --report-out runs/golden_v2/reports/pilot_preflight.json \
  --markdown-out runs/golden_v2/reports/pilot_preflight.md

# 3a. Pilot 文件候选池
linkrag-eval golden-v2 candidate-pool \
  --seeds runs/golden_v2/seeds/query_seeds.jsonl \
  --chunks runs/golden_v2/seeds/chunk_records.jsonl \
  --out runs/golden_v2/candidates/candidate_pool_file.jsonl

# 3b. 活栈多源候选池
# 10w 背景库建议先回填 alt embedding sidecar,避免候选池构建时临时编码全部 chunk
linkrag-eval golden-v2 alt-embed-backfill \
  --dataset-ids 990201,990202 \
  --batch 100

linkrag-eval golden-v2 candidate-pool-live \
  --seeds runs/golden_v2/seeds/query_seeds.jsonl \
  --dataset-ids 990201,990202 \
  --sources bm25,dense,sparse,alt_embedding \
  --dense-score-threshold 0.0 \
  --sparse-score-threshold 0.0 \
  --alt-score-threshold -1.0 \
  --out runs/golden_v2/candidates/candidate_pool.jsonl

# 4. DeepSeek 标注
linkrag-eval golden-v2 label \
  --candidates runs/golden_v2/candidates/candidate_pool.jsonl \
  --out runs/golden_v2/judgments/deepseek_judgments.jsonl

# 5. 标注 QC 门禁
linkrag-eval golden-v2 qc \
  --judgments runs/golden_v2/judgments/deepseek_judgments.jsonl \
  --report-out runs/golden_v2/judgments/deepseek_judgments_qc.json \
  --markdown-out runs/golden_v2/judgments/deepseek_judgments_qc.md

# 6. 高风险样本复核队列
linkrag-eval golden-v2 review-queue \
  --judgments runs/golden_v2/judgments/deepseek_judgments.jsonl \
  --out runs/golden_v2/judgments/deepseek_judgments_review_queue.jsonl \
  --report-out runs/golden_v2/judgments/deepseek_judgments_review_queue_report.json

# 7. 第二判官复判(正式运行必须换成非 DeepSeek 同源模型)
linkrag-eval golden-v2 review-label \
  --review-queue runs/golden_v2/judgments/deepseek_judgments_review_queue.jsonl \
  --candidate-pool runs/golden_v2/candidates/candidate_pool.jsonl \
  --out runs/golden_v2/judgments/review_judgments.jsonl \
  --report-out runs/golden_v2/judgments/review_judgments_report.json \
  --reviewer-model another-judge-model

# 8. 仲裁合并
linkrag-eval golden-v2 adjudicate \
  --judgments runs/golden_v2/judgments/deepseek_judgments.jsonl \
  --reviews runs/golden_v2/judgments/review_judgments.jsonl \
  --out runs/golden_v2/judgments/adjudicated_judgments.jsonl \
  --report-out runs/golden_v2/judgments/adjudication_report.json \
  --policy manual_on_conflict \
  --conflict-out runs/golden_v2/judgments/manual_conflicts.jsonl

# 9. 构建三套黄金集
linkrag-eval golden-v2 build \
  --judgments runs/golden_v2/judgments/adjudicated_judgments.jsonl \
  --out-dir runs/golden_v2/golden \
  --tune-ratio 0.70

# 10. 主验收:blind + chunk
linkrag-eval run \
  --golden runs/golden_v2/golden/realistic_blind.jsonl \
  --precheck \
  --require-chunk-references \
  --sparse-score-threshold 0.0
```

## 十二、实施顺序

### Step 0:Spark 离线预生成原料池

- 使用 Codex sub-agent `gpt-5.3-codex-spark` 批量生成语料草稿、预切 chunk、query seeds、hard case seeds。
- 输出到 `runs/golden_v2/spark_pregen/`,包含 `bundle_manifest.json` 和各 jsonl 文件 hash。
- 导入器只校验和消费离线 bundle,不得调用 `.env.eval` 中的项目模型补生成。

验收:

- manifest 中 `generator.model` 固定为 `gpt-5.3-codex-spark`。
- 产物不包含 API key,不包含最终 `expected_chunk_ids`。
- report 展示 source/type/hard_reason/重复率/泄漏检测统计。

### Step 1:指标与报告口径固化

- 聚合层按 chunk/doc 分名。
- HTML/JSON/DB 不再混合 headline。
- `run --require-chunk-references` 作为主评测默认建议。

验收:

- doc-only golden 跑 strict 模式会失败。
- 混合 golden 输出 `recall_chunk` 与 `recall_doc`,不输出混合均值。

### Step 1.5:Spark chunk 导出并入库

- `golden-v2 spark-corpus-export` 将标准化 `chunk_records.jsonl` 导出为现有 `ingest` 可消费的 `collection.tsv` 与 `manifest.jsonl`。
- `manifest.jsonl` 允许携带 `ordinal`,保证同一 doc 多 chunk 时 deterministic `chunk_id` 不漂移。
- 后续仍走 `linkrag-eval ingest` 写 eval MySQL + Qdrant,不直接写生产库或 eval 表。

验收:

- 导出的 collection pid 唯一,manifest doc_id/status/ordinal 完整。
- `linkrag-eval ingest --dataset-id 990901 ...` 只写 `tolink_rag_eval_db` 与 eval Qdrant 前缀。
- `bm25-backfill --dataset-ids 990901` 后 SQLite FTS5 可检索该批语料。

### Step 2:开源数据 chunk 化

- `golden-opensource --reference-granularity chunk` 从 `eval_corpus_chunk` 映射正例 doc 的 chunk。
- 原 doc 粒度只作为诊断保留。

验收:

- 新生成 golden 中 `expected_chunk_ids` 覆盖率 >= 95%。

### Step 3:SQLite FTS5 BM25 候选源

- 使用 `EVAL_BM25_MODE=sqlite_fts5`。
- `bm25-backfill` 从 eval MySQL 重建 BM25 sidecar。
- 候选池模块读取 SQLite BM25 topN。

验收:

- BM25 查询不访问 Qdrant。
- BM25 backfill 后 `eval_corpus_chunk.bm25_indexed=True`。

### Step 4:候选池与 DeepSeek 标注

- 实现 dense/BM25/alt/random 合并去重。
- DeepSeek 对候选逐条判定。
- 标注结果可续跑。

验收:

- 每条 query 有候选来源分布。
- random false positive 可统计。
- 当前系统 missed 但相关的样本可进入 Hard Set。

### Step 5:三套集合与 tune/blind 拆分

- 构建 regression、realistic、hard。
- 每套再拆 tune/blind。
- 报告 headline 只看 realistic blind chunk。

验收:

- 调参只用 tune。
- 最终验收只用 blind。
- hard set 单列,不静默混入 realistic。

## 十三、验收标准

首版 v2 完成后必须产出:

1. `realistic_blind.jsonl`:不少于 100 条,`expected_chunk_ids` 覆盖率 >= 95%。
2. `hard_blind.jsonl`:不少于 50 条,至少覆盖 5 类 hard reason。
3. `build_report.md`:含来源、长度、role、split、判官质量统计。
4. `run` 报告:headline 为 `recall_chunk@10` / `mrr_chunk`。
5. 旧 regression set 仍可跑,但报告明确标记非真实能力分。
6. scale-up 验收分阶段做:pilot 链路全绿后再扩 2w,2w 指标和成本稳定后再扩 10w;10w 阶段主报告使用 500-1000 条 realistic blind query,不是把 query 数扩到 10w。

## 十四、风险与处理

| 风险 | 影响 | 处理 |
| --- | --- | --- |
| DeepSeek 判官偏宽 | 误把无关 chunk 标相关 | random candidates 估计 false positive;高风险样本双判官 |
| 真实 query 无可答 chunk | 主集噪声升高 | 标为 unresolved,不进主集;单独统计语料覆盖缺口 |
| alt embedding 与当前模型同源 | 候选池仍偏向当前能力 | 固定使用不同 provider/model |
| hard set 拉低总分 | 数字不可解释 | hard set 单列,不并入 realistic headline |
| tune/blind 泄漏 | 验收偏乐观 | query hash + 同源样本同 split |
| Spark 预生成与项目配置模型混用 | 难以判断数据偏差来源 | 生成侧只允许 `gpt-5.3-codex-spark`;项目模型只用于 eval 运行和 DeepSeek 标注 |

## 十五、当前代码状态

截至本文新增时,仓库已具备部分前置能力:

- `run --require-chunk-references` 可拒绝 doc-only golden。
- `run --dense-score-threshold/--sparse-score-threshold` 可做活栈阈值复验;Ark sparse pilot 已确认 `0.40` 会过滤掉有效候选。
- 聚合指标已支持 chunk/doc 分名。
- `golden-opensource --reference-granularity chunk` 可从 eval chunk 收缩 reference。
- BM25 已新增 `sqlite_fts5` 模式与 `bm25-backfill` 入口。
- `golden-v2 spark-import` 已支持 Spark 离线 bundle 的模型、hash、schema、chunk_id 和泄漏词校验,并输出标准化 seeds/report。
- `golden-v2 spark-corpus-export` 已支持将 Spark chunk_records 导出现有 ingest 的 collection/manifest 输入。
- `golden-v2 seed-import` 已支持将真实 query/客服/日志/开源 query 的 JSONL/TSV/CSV 清洗成标准 `query_seeds.jsonl`,默认过滤重复、过短/过长、手机号/邮箱/身份证号和密钥形态文本。
- `golden-v2 pilot-preflight` 已支持 pilot 本地门禁:检查 query seed 数量、dataset_id、eval MySQL/Qdrant 隔离、judge 配置、第二判官差异、alt embedding 独立配置和 BM25 模式。
- `golden-v2 pilot-plan` 已支持生成从真实 query 导入、预检、BM25/alt 回填、候选池、DeepSeek 标注、QC、复核、仲裁、build、blind run 到 medium 2w scale-plan 的完整命令清单。
- `golden-v2 candidate-pool` 已支持 pilot 文件模式(`bm25_local + random_neighbor`)并输出候选池/report。
- `golden-v2 candidate-pool-live` 已支持活栈多源模式(`bm25_sqlite_fts5 + current_dense + current_sparse + alt_embedding + random_neighbor`),并用 RRF 单路口径与候选池专用阈值避免正式评测权重/阈值污染候选池;report 会记录 dense/sparse/alt embedding 各路阈值。
- `golden-v2 alt-embed-backfill` 已支持将 alt embedding 写入 SQLite sidecar;`candidate-pool-live` 会优先复用缓存,缺失 chunk 自动补齐。
- `golden-v2 label` 已支持通过 eval 独立 judge client 对候选 chunk 判相关性并输出 judgments/report。
- `golden-v2 qc` 已支持 judgments 门禁:random relevant rate、unresolved rate、来源覆盖和 Markdown/JSON 报告。
- `golden-v2 review-queue` 已支持抽取高风险复核队列:random relevant、unresolved query、缺少 alt positive 支持的正例。
- `golden-v2 review-label` 已支持用指定 `--reviewer-model` 对 review queue 做第二判官复判,并从 candidate_pool 回填 chunk 正文。
- `golden-v2 adjudicate` 已支持 `review_overrides` 与 `manual_on_conflict` 两种策略;后者在主判官/第二判官冲突时保留原判并输出人工复核队列,避免冲突样本直接进入主 golden。
- `golden-v2 build` 已支持从 judgments 构建 `realistic/hard × tune/blind` 四套 chunk 粒度 golden。
- `golden-v2 scale-plan` 已支持为 medium/10w 背景库生成分批 Spark bundle、ingest、BM25 回填、alt embedding 回填命令草稿,并输出 judge/embedding 规模估算报告。
- alt embedding 候选搜索已从 CLI 拆到独立模块,默认使用 NumPy 向量化 cosine topK;无 NumPy 时退回按 dataset 分组的纯 Python topK。

待实现:

- alt embedding 更大规模性能优化:10w 先用 SQLite sidecar + NumPy 向量化扫描;若继续放大到数十万/百万级,再升级为嵌入式 ANN/HNSW sidecar。
- 仲裁策略继续扩展:当前已有"复判覆盖"和"冲突进人工队列";后续可加第三判官自动裁决。
- 10w 背景库实际执行:按 `scale-plan` 产出的 batch_specs 调 Spark 子 Agent 分批生成,再逐批 ingest / backfill / QC。
