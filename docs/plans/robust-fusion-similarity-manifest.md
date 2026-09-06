# Gate A 实验相似度 manifest

> 记录：`ROBUST-FUSION-SIMILARITY-MANIFEST-2026-08-29-v10`
> 对应科研协议：`ROBUST-FUSION-RESEARCH-2026-08-29-v29`
> 状态：v1 的 28 个 Dev 参照集合、84 个双编码器分数、A/B 与仲裁全部只读封存；人工效度 PASS、共同支持 17.86%/57.14% 的正式结论永久为 `INCONCLUSIVE`。唯一一次 72-family pre-Gate Dev 共同支持补充已完成四提交先锁后验与零仲裁单次终审；combined 共同支持 96%/99% PASS，但 supplement-only/combined 人工效度均为 `INCONCLUSIVE`，故联合结论 terminal `INCONCLUSIVE`。正式标准化/分带数值未冻结，本文件当前**不能**授权 Gate A，且 P2 不得第三轮补充。
> 结果边界：Gate A/B 均未运行；所有待填项必须由 Dev/外部制品确定。
> `GATE_A_AUTHORIZATION: false`

## 1. 唯一测量对象

对 Query (q)、唯一目标等价组 (g) 和待测候选 (c)：

\[
S_{qg}(c)=\max_{h\in A_{qg}}\cos(z(c),z(h)),
\]

其中 (A_{qg}) 是 Clean 池内已确认属于目标组 (g) 的正确参照 Chunk 集。该量不是 Query—Chunk 相似度，也不是 M1 的候选—Top-M 邻居相似度。

每个确认性候选只能引用一个 `target_equivalence_group_id`。若目标组为空、多义、跨 split 或含 unresolved 成员，manifest 校验必须拒绝该候选。

## 2. 当前制品状态

| 项 | 当前值 | 冻结状态 |
| --- | --- | --- |
| 主实验编码器 | `intfloat/multilingual-e5-base@d128750597153bb5987e10b1c3493a34e5a4502a` | `DEV_HUMAN_VALIDITY_PASS_FORMAL_FREEZE_BLOCKED`；不得用于 Gate A 结果读取 |
| 已淘汰候选 | BGE-M3、本地 BGE 服务与既有 BGE sidecar | 禁止进入 Gate A route、\(S_{qg}(c)\) 或独立审计 |
| 既有 Alt Embedding | 20,772 条历史 BGE-M3 向量；model key 仅记录模型名、服务 URL、维度 | 只作历史资产解释，不合格用于确认性逐值重放或候选筛选 |
| 独立相似性审计编码器 | `sentence-transformers/distiluse-base-multilingual-cased-v2@bfe45d0732ca50787611c0fe107ba278c7f3f889` | `DEV_HUMAN_VALIDITY_PASS_FORMAL_FREEZE_BLOCKED`；128-token 上限，已按长度分层报告 |
| 无标签资格制品 | `ROBUST-FUSION-SIMILARITY-ENCODER-QUALIFICATION-2026-08-28-v3`，manifest SHA-256 `931946bd244d794bf390d5c37f166308d010870b429919b1167131fd0ceb1f2a` | 两个模型均 PASS；只同步已冻结的 Reranker 独立性口径，不是 Gate A 解锁证据 |
| 两个被测 Reranker 家族 | `Qwen/Qwen3-Reranker-0.6B@e61197ed…`（生成式）与 `jinaai/jina-reranker-v2-base-multilingual@9cfeff2d…`（跨编码器） | `ROBUST-FUSION-RERANKER-QUALIFICATION-2026-08-28-v2` 已冻结选择，manifest SHA-256 `96c49a3e58ff167bf675c413e32336c659f6899aca2f7351faa59e1c2ef26f43`；P3-05 仍待资源与 Dev 契约完成 |
| Learned Sparse route | `ark / doubao-embedding-vision-251215` 在线 API | 只提供检索路分数/排名，不定义实验相似度 |
| Dev 自动校准制品 | `ROBUST-FUSION-SIMILARITY-DEV-CALIBRATION-2026-08-29-v1`，manifest SHA-256 `b44d13f5…454c` | 不可变基础制品保留当时的 `AWAITING_HUMAN_SUBMISSIONS`；后续最终审阅另行封存，Gate A/B=false |
| 数据源内均值/标准差 | provisional `0.9841916433456961 / 0.01442102645074964`，`ddof=1` | 人工效度 PASS 已满足；共同支持 FAIL，当前未冻结 |
| 共同支持区间与最低覆盖 | 观测范围交集 `[0.9843160362038024, 0.9955983802559442]`；两侧最低 60% | 等价/冲突覆盖 17.86%/57.14%，自动 FAIL；不得放宽 |
| 低/高/模糊分带 | provisional pooled q25/q75：low `≤0.9770479717675954`、high `≥0.9951423425431406` | 人工效度已通过，但共同支持未通过；正式数值未冻结 |
| 正式人工包 | A/B 各 24 行；manifest `6a4ca9b0…3e9` / `3b9e1626…92db` | 两份真实提交已锁定，机械校验 PASS |
| 双人一致性 | 二次加权 κ=`0.9484240688`；±1 分一致率=`100%` | 均通过 `0.60/90%` 冻结门槛 |
| 仲裁与最终人工分数 | 8 条强制项 + 1 条其余非一致项，共 9 行；仲裁锁 `631d9281…61cf`；最终 manifest `463c31cb…647d` | 9/9 机械校验 PASS；24 条最终分数齐备 |
| 仲裁后人工效度 | E5 overall/short/long=`0.6320/0.5741/0.5811`；DistilUSE overall=`0.4873`；最高带中位数/≥4 比例=`4.0/100%` | 六项冻结门槛全部 PASS；`human_measurement_decision=PASS` |
| 联合冻结判定 | 人工效度 PASS + 共同支持 FAIL | `INCONCLUSIVE`；P2-01/P2-04 未完成 |
| 唯一共同支持补充 | 72 个新成对 family；v1+补充总 family=100；预注册 lock `57179fbf…c6b2b`；自动 manifest `1c8b0499…327d`；final manifest `ea40f4f0…f2b35` | A/B 关系 144/144、相似度 48/48 exact，零仲裁。combined 共同支持 96%/99% PASS；supplement-only/combined E5 overall=`0.1775/0.3968` 未达 0.50，人工效度均 `INCONCLUSIVE`；terminal `INCONCLUSIVE`，无正式数值冻结 |

Learned Sparse 是被研究系统的一条召回路，实验相似度则是用于刻画压力条件的独立测量工具。两者不能因都叫“embedding”而混为同一变量，也不能用豆包 sparse 权重代替候选—正确参照的 dense cosine。

### 2.1 BGE-M3 淘汰记录

2026-08-28 在 Gate A/B 均未运行、没有查看任何确认性结果时，研究负责人纠正真实系统口径并明确淘汰 BGE-M3。真实三路固定为：

- Dense：`text-embedding-v4` 在线 API；
- Learned Sparse：`ark / doubao-embedding-vision-251215` 在线 API；
- BM25：eval 自持 SQLite FTS5。

此前对 BGE-M3 官方制品的只读审计仍作为 v2 历史记录保留，但不再赋予候选资格。本轮作废理由不是 Gate 结果，而是：

1. BGE-M3 已不是当前 Learned Sparse route，历史注释把它写成“生产实际 sparse”与真实 `.env.eval` 冲突；
2. 既有 BGE sidecar 缺精确输入和服务 fingerprint，不能逐值重放；
3. 中间件本地 `tokenizer.json` 摘要与此前固定官方 revision 的摘要不一致，版本身份未闭合；
4. 研究负责人明确要求淘汰，继续投入探针和下载成本不符合当前研究口径。

刚生成但未进入任何 Gate 输入的 BGE 探针已从研究运行目录移入本机废纸篓。任何 seal 工具发现 `encoder.model_id`、route provider 或独立审计编码器含 `bge-m3`/`BGE-M3` 时必须拒绝。

### 2.2 非 BGE 资格预选

新主编码器必须输出适合候选—参照 cosine 的 dense 向量，覆盖中英文，具有可冻结的模型身份和输入口径，并与两个被测 Reranker 的输出制品分离。不得使用 Learned Sparse route 本身充当 \(S_{qg}(c)\)，也不得因现有缓存或 Gate 结果选择模型。

在不读取 Dev、Gate A、Blind 或任何排序结果的前提下，预先按“中英文覆盖、公开许可、精确 revision、学生预算、可本地封存、主/审计架构分离”筛选并运行固定合成探针：

| 角色 | 预选制品 | 架构与许可 | 输入上限 | 资格结论 |
| --- | --- | --- | --- | --- |
| 主编码器 | `multilingual-e5-base@d1287505…` | XLM-RoBERTa multilingual E5；MIT | 512 tokens | 精确权重、配置、tokenizer 摘要与正逆序 float32 向量重放通过 |
| 独立审计 | `distiluse-base-multilingual-cased-v2@bfe45d07…` | multilingual DistilBERT sentence encoder；Apache-2.0 | 128 tokens | 精确权重、配置、tokenizer 摘要与正逆序 float32 向量重放通过；只作长度分层审计 |

`Alibaba-NLP/gte-multilingual-base` 因需要自定义 remote code、multilingual MPNet 因 128-token 上限但成本接近主模型、LaBSE 因主权重约 1.88 GB，均在运行探针前排除。资格制品只证明身份和确定性。已冻结的 Qwen/Jina manifest 证明两者不复用这两个 encoder artifact；相似度测量仍须在 Dev 完成长短文本分层的独立编码器—盲人工一致性检查。

若以后改用在线 API，必须把请求 schema、模型 ID、端点身份摘要、固定探针、每批响应向量摘要和正式候选快照一起 seal；如果提供方不公开权重 revision，要明确记录为 provider-managed，并依赖封存输出而不是声称权重可本地复现。

### 2.3 已实例化的编码契约

| 字段 | 主编码器 | 独立审计编码器 |
| --- | --- | --- |
| tokenizer | 与模型同 ID、同 exact revision | 与模型同 ID、同 exact revision |
| 文本标准化 | HTML entity 解码；BR/IMG/tag 转空格；NFKC；Unicode 空白折叠并去首尾 | 同主编码器 |
| prefix | 所有候选和参照统一加 `query: `（对称相似度） | 空字符串 |
| 截断 | 右截断，512 tokens，加入 special tokens | 右截断，128 tokens，加入 special tokens |
| pooling | attention-mask mean pooling，随后 Normalize | attention-mask mean pooling，随后 Dense 768→512 + Tanh |
| 向量 | 输出 768 维，float32，L2 normalize | 输出 512 维，float32，L2 normalize |
| cosine | float32 输入、float64 累积，不作存储舍入 | 同主编码器 |

资格运行固定 `sentence-transformers==5.7.0`、Python 3.11.15、Torch 2.13.0、Transformers 5.16.1、NumPy 2.4.6、CPU 单线程和 deterministic algorithms。主权重 SHA-256 为 `a18a44fa…09a7`；审计编码器 Transformer 与 Dense 权重 SHA-256 分别为 `e8c2aed2…64d7`、`0a21b1ce…91ed`。完整文件大小、tokenizer/config 摘要、探针向量摘要和代码摘要以 v2 资格制品为准。

## 3. 编码器与实现必填项

以下字段不得留空或使用 `latest/main`：

```text
encoder:
  model_id:
  exact_revision:
  upstream_commit:
  license:
  weight_files:
    - relative_path:
      size_bytes:
      sha256:
  tokenizer_id:
  tokenizer_revision:
  tokenizer_files_sha256:
  implementation_package:
  implementation_version:
  implementation_commit:
  device_class:
  deterministic_flags:
```

若使用远端编码服务，还必须记录：

```text
service:
  endpoint_identity_hash:
  image_or_build_digest:
  model_load_command_hash:
  response_schema_version:
  server_side_preprocessing:
  server_side_pooling:
  server_side_normalization:
  conformance_probe_sha256:
```

endpoint 原文、密钥和内部凭据不得进入研究 manifest；只保存可区分服务实现且不泄密的摘要。

## 4. 输入与向量计算必填项

```text
input:
  source_text_field:
  unicode_normalization:
  whitespace_policy:
  html_policy:
  query_or_passage_prefix:
  separator:
  max_tokens:
  truncation_side:
  add_special_tokens:

embedding:
  pooling:
  output_layer:
  output_dimension:
  pre_normalization_dtype:
  l2_normalize:
  stored_dtype:
  cosine_accumulation_dtype:
  score_rounding_for_storage:
  allowed_score_range:
```

主分析必须使用未四舍五入的计算值；展示可以另行格式化。NaN、Inf、零范数、维度不符或超出声明范围时拒绝样本，不能静默置零。

## 5. 目标参照集合必填项

每个 `query_id × target_equivalence_group_id` 保存：

```text
reference_set:
  dataset_id:
  dataset_revision:
  cohort_id:
  split_role:
  query_id:
  target_equivalence_group_id:
  members:
    - official_record_id:
      local_chunk_id:
      source_document_id:
      raw_content_sha256:
      normalized_input_sha256:
      vector_sha256:
      relevance_status:
      adjudication_record_id:
  member_order_rule:
  set_membership_sha256:
```

成员顺序按 `official_record_id` 的 UTF-8 字节序确定；取最大余弦时如有并列，`argmax_reference_id` 使用同一顺序的第一项。该并列规则不影响 (S_{qg}(c))，但保证逐条诊断可重放。

## 6. 候选分数记录

```text
candidate_similarity:
  query_id:
  target_equivalence_group_id:
  candidate_chunk_id:
  candidate_raw_content_sha256:
  candidate_normalized_input_sha256:
  candidate_vector_sha256:
  max_cosine_similarity:
  argmax_reference_id:
  encoder_manifest_sha256:
  computation_code_sha256:
  computation_config_sha256:
```

每个候选只存一行主相似度。H2 使用压力链内 20 个候选的相似度均值形成条件级预测量，不把同一个池级排序伤害复制为 20 行。

## 7. 数据源内 Dev 冻结项

对每个候选主数据集，Dev 上合并事实等价与事实冲突候选后填写。Internal v6-Dev 的自动部分和人工效度已经实例化，但正式数值仍受共同支持门禁约束：

```text
dataset_calibration:
  dataset_id:
  dev_snapshot_sha256:
  eligible_candidate_count:
  equivalent_count:
  factual_conflict_count:
  mean:
  standard_deviation:
  standardization_ddof:
  common_support_rule:
  common_support_interval:
  minimum_common_support_coverage:
  low_band:
  ambiguous_band:
  high_band:
  adjacent_sensitivity_boundaries:
  independent_encoder_audit_rule:
  blind_human_similarity_scale:
  frozen_at:
```

等价与冲突共用同一数据源内分带；阈值不能按 Reranker、LTR-v3 或 Gate A 结果分别调整。共同支持以关系两侧均有真实覆盖为前提，排除尾部和覆盖率必须报告。

Internal v6-Dev 的结果前规则现固定为：均值/标准差使用合并后的 56 条 eligible 候选及 `ddof=1`；共同支持取两类观测范围交集，并要求两侧覆盖率均不低于 60%；主分带取合并 eligible 候选的 q25/q75，q30/q70 与 q20/q80 为相邻敏感性。关系内 q10–q90 交集的首次自动尝试为空，失败目录保留；它发生在任何人工提交和 Gate 结果之前。改用观测范围交集并不把覆盖不足改写为通过，60% 独立门禁已经在本批明确失败。

盲人工抽样固定为 24 对：`target_relation × relative-length` 六格各 4 条，格内覆盖两个编码器 percentile-rank gap 的低/高端，并保证四类冲突总体覆盖。两名研究员均使用 1–5 相似度量表；分差至少 2 或任一 `uncertain=yes` 必须仲裁。二次加权 κ 下限 0.60、±1 分一致率下限 0.90；最终模型效度还需满足 E5 overall Spearman≥0.50、长短各≥0.30、DistilUSE overall≥0.40，以及最高主分带人工中位数≥4、至少 70% 得分≥4。全部细则和失败/不确定后果由自动制品 `human_audit_rules.json` 封存。

## 8. 重放与合格判定

正式 manifest 只有同时满足下列条件才合格：

1. 编码器、tokenizer、权重、实现和输入规则全部有精确版本与摘要；
2. 参照成员、候选输入、向量和计算代码均可由内容摘要追溯；
3. 固定探针在独立重跑中向量维度、范数和余弦逐值满足预先冻结容差；
4. 数据源内 Dev 统计、分带、共同支持和最低覆盖已经时间戳冻结；
5. 独立编码器与盲人工量表审计规则已经冻结；
6. manifest 自身 SHA-256 已进入 Gate A root manifest；
7. 任一 `UNFROZEN` 字段存在时，seal 工具必须拒绝 Gate A 模式。

## 9. 下一步

研究负责人已在 Gate A/B 未运行、Dev 排序效果未读取时确认 `Qwen3-Reranker-0.6B@e61197ed…`（生成式）与 `jina-reranker-v2-base-multilingual@9cfeff2d…`（跨编码器）。P2-01 v1 自动、A/B、双人一致性和 9 行真实仲裁均已完成；六项人工效度门槛全部 PASS，但共同支持失败，v1 永久为 `INCONCLUSIVE`。唯一一次补充也已终审：共同支持 PASS，supplement-only/combined 人工效度 `INCONCLUSIVE`，联合状态 terminal `INCONCLUSIVE`。不得冻结 provisional 数值、再扩 P2 样本、换编码器或降低门槛；P2-01/P2-04 保持未完成，`GATE_A_AUTHORIZATION: false`。下一动作只能由研究负责人决定是否以新研究 ID 重设研究方案或停止当前 Gate 主线，当前协议下不得进入 readiness/Gate。

## 10. 变更记录

### v10

- 四份真实补充提交先锁后验：关系 144/144、相似度 48/48 完全一致且零仲裁；提交锁 `7a3ca434…2ae6`；
- 锁后发现零仲裁 finalizer 缺失；以不修改预注册的 post-lock executor 补齐，合成测试后先封存 implementation manifest `af35908b…499fb`，再单次运行；
- supplement-only 共同支持 66.67%/75.00%，combined 96.00%/99.00%，均通过 60%；但 supplement-only/combined E5 overall Spearman 0.1775/0.3968 未达 0.50，人工效度均为 `INCONCLUSIVE`；
- 联合结论 terminal `INCONCLUSIVE`；final manifest `ea40f4f0…f2b35`，不生成正式标准化/分带数值，P2-01/P2-04 与 Gate 未完成，无第三轮。

### v9

- 永久保留 v1 的 17.86%/57.14% 与正式 `INCONCLUSIVE`，不覆盖、筛除或重新仲裁；
- 在任何补充分数和人工结果前锁定唯一一次 72-family pre-Gate Dev 补充：总 family=100、每侧 combined 分母=100，缺失/无效按 miss，不早停、不扩第三轮；
- 本地冻结 E5/DistilUSE 生成 216×768/512 向量和 144 个候选分数，二次内存重放 exact；形成 A/B 各 144 行关系包与各 48 行相似度包；
- 构造角色预览只作诊断，不能替代人工关系真值或冻结数值；当前 `AWAITING_HUMAN_SUBMISSIONS`，Gate A/B 未授权。

### v8

- 在读取仲裁内容前锁定 9 行真实提交，仲裁 SHA-256 `888f0915…163d`、仲裁锁 SHA-256 `631d9281…61cf`；机械校验确认 ID 集合、唯一性、1–5 枚举、仲裁员标识和理由全部合法；
- 形成 24 条唯一最终人工分数；E5 overall/short/long、DistilUSE overall、最高主分带中位数与高分比例六项冻结阈值全部 PASS，人工测量效度判为 `PASS`；
- 共同支持覆盖仍为 17.86%/57.14%，低于双方 60% 下限，故联合冻结判为 `INCONCLUSIVE`，provisional 标准化与分带不升级，P2-01/P2-04 和 Gate 授权仍未完成；
- 完成描述性统计边界与 11/11 谬误扫描；不作总体人口、因果或确认性效果声称。

### v7

- 在读取评分内容前锁定 A/B 两份真实提交，保留文件大小、角色包 manifest 与提交 SHA-256；
- 机械校验确认 A/B 各 24/24 行、ID/枚举/不确定说明均合法；二次加权 κ=0.9484240688、±1 分一致率=100%，双人一致性门禁 PASS；
- 生成 9 行盲化人工仲裁包：覆盖全部 8 条强制仲裁项及其余 1 条非一致项，以形成唯一最终人评分；Codex/模型/工具不得代填；
- 状态转为 `AWAITING_HUMAN_ADJUDICATION`；人工效度、正式标准化/分带和 Gate 授权仍未完成。

### v6

- 只读绑定经核验的 Internal v6-Dev route evidence v5 与其 adjudicated release，封存 28 个唯一目标参照集合；
- 用冻结 E5/DistilUSE 对 112 条 Chunk 编码并计算 84 个非参照候选的目标组最大余弦，保存输入、向量、代码与配置摘要；
- 冻结数据源内标准化、共同支持最低覆盖、q25/q75 主分带、相邻敏感性和 24 对盲人工审计的结果前规则；
- 透明记录共同支持覆盖为 17.86%/57.14%，低于双方 60% 下限，因此 provisional 数值不能正式冻结；
- 生成 A/B 各 24 行、物理隔离且无答案键的正式包，状态固定为 `AWAITING_HUMAN_SUBMISSIONS`；不完成 P2-01/P2-04，不授权 Gate A。

### v5

- 在 Gate A/B 与 Dev 排序效果均不可见时，按研究负责人决定冻结 Qwen3 0.6B 生成式 Reranker 与 Jina v2 multilingual 跨编码器；
- 记录 Jina 的官方固定制品、独立学术采用 DOI 和“采用不等于最优”的主张边界；
- 由 v3 编码器资格制品复核两个相似度编码器与冻结 Reranker 均无制品复用；
- 保持资源、Dev 效度、共同支持和分带门禁未完成，Gate A 继续不授权。

### v4

- 在选择标准和候选集合固定后、读取任何研究数据前，资格预选 `multilingual-e5-base` 为主相似度编码器、multilingual DistilUSE 为独立审计编码器；
- 固定两者 exact revision、许可、权重/config/tokenizer 摘要、输入前缀、截断、pooling、维度、归一化和数值精度；
- 固定资格制品及其正逆序重放结果，同时明确它只关闭模型身份/确定性，不关闭 Reranker 独立性或 Dev 效度/分带门禁；
- 保持 Gate A 未授权，避免把固定合成探针或模型资格误写成现象结果。

### v3

- 依据研究负责人纠正，淘汰 BGE-M3 作为 route、主相似度编码器和独立审计编码器的全部资格；
- 冻结真实三路为 `text-embedding-v4` Dense、Ark/豆包 Learned Sparse、SQLite FTS5 BM25；
- 明确 Learned Sparse route 与 \(S_{qg}(c)\) 的 dense cosine 是两个不同对象；
- BGE 历史 sidecar 只保留资产追溯，禁止进入 Gate A；主相似度编码器回到重新选择门禁。

### v2（历史，已被 v3 的淘汰决定覆盖）

- 固定并审计 BGE-M3 候选的官方 revision、许可、主权重和两个 tokenizer 大文件摘要；
- 明确官方 8,192-token 能力与实现默认 512-token 截断不是同一冻结项；
- 把候选状态从“只知道模型名”推进为“官方制品资格通过”，同时保留主编码器 `UNFROZEN` 门禁；
- 明确旧 sidecar 不能因模型名相同而直接复用，以及升级为正式编码器前的六项验收。
