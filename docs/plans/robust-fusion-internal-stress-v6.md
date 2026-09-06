# Internal Stress v6 数据协议

> 记录：`ROBUST-FUSION-INTERNAL-STRESS-2026-08-29-v13`
> 日期：2026-08-29
> 状态：数据身份、三分目录、访问锁、摄取 schema 与来源资格台账已正式建立；P2-05 已通过；受控合成 30-family v6-Dev 已完成 A/B 双审、提交锁定与主持人仲裁，人工接纳 28/30。Dev 三路执行的 v2/v3 失败与 v4 完整性拒收均原样保留；独立 v5 已在真实三路和 Qdrant 上完成并核验。C2 三分边界补充仍为空白规划包；GateA/Blind 人口仍为空且不得解锁。
> 上位协议：[科研协议](https://github.com/ql-link/LinkRag-Eval/blob/50f3a9b0ead581fb17fc3e4080c70361c9f24475/docs/plans/robust-fusion-research.md)、[工程实施协议](https://github.com/ql-link/LinkRag-Eval/blob/50f3a9b0ead581fb17fc3e4080c70361c9f24475/docs/plans/robust-fusion-engineering.md)、[研究推进清单](https://github.com/ql-link/LinkRag-Eval/blob/50f3a9b0ead581fb17fc3e4080c70361c9f24475/docs/plans/robust-fusion-todo.md)。

## 1. 当前结论

Internal Stress v6 现在是一个正式、可核验的数据对象，而不再只是协议中的名称：

- 唯一记录为 `ROBUST-FUSION-INTERNAL-STRESS-2026-08-29-v13`；
- 本地忽略目录固定为 `data/robust_fusion/internal_stress_v6/`；
- `internal-v6-dev`、`internal-v6-gatea`、`internal-v6-blind` 分别有独立目录、manifest 与访问状态；
- 最小 Query、文档、证据和 family assignment 摄取表已建立；
- 分享包、SQLite 数据集、检索缓存、历史 Blind 和 `ssh linkcv` 的资格边界已经逐项登记；
- 全包由 `manifest.sha256` 校验，当前文件权限为目录 `0700`、文件 `0600`。

但“正式建立”不等于“已经有确认性样本”。分享包、本地工作 SQLite 和远端旧 eval MySQL 均为 `eval_query=0`、`eval_qrel=0`；服务器也没有另一份 LinkRag-Eval 行级包。研究负责人已经在查看任何 30-family 产出前授权 DeepSeek 生成受控合成 v6-Dev family，并由人工最终复核；该授权只关闭 Dev 先导的来源路径阻塞，不会凭空产生 Gate 人口。因此 v6 当前状态固定为：

```text
FORMALLY_ESTABLISHED_DEV_SYNTHETIC_REVIEW_ADJUDICATED_ROUTE_EVIDENCE_VERIFIED
Gate eligibility: NOT_ELIGIBLE
```

Dev 双人复核、仲裁和人工接纳率已经完成，但独立自然来源 Query family、正确证据、跨 cohort family 隔离与功效分母仍未完成。因此 P3-04 只能记为“正式骨架与 Dev 合成先导完成、确认性人口未完成”，不能标成全部完成。

> **概念解释｜正式建立与正式可运行**：正式建立表示数据 ID、字段、边界、目录和校验规则已经存在；正式可运行还要求真实样本、真值、隔离和封存全部通过。前者防止后续随意改口径，后者才允许进入 Gate。

## 2. 分享包在本研究中的正式地位

`linkrag-eval-sqlite-share-20260827` 不是无关的历史备份，而是本研究想法的实证与工程起点。它有三项正式作用：

1. **假设来源**：历史三路召回、融合、Reranker 与 Blind 工程结果暴露了“候选池结构可能影响排序鲁棒性”这一问题，形成当前研究问题的经验来源；
2. **可行性与预算证据**：它证明 Dense、Learned Sparse、BM25、LTR-v3、SQLite、Qdrant 和本地缓存链路真实存在，可用于估算重建候选与实验成本；
3. **工程复用底座**：与 `.env.eval` 指向的旧 eval MySQL、当前 Qdrant、BM25 和 Alt Embedding 对账后，可复用已验证的 ID/provenance、部分索引覆盖、模型/运行指纹和经逐集复核合格的语料材料。

它不能承担的角色同样固定：

- 不能把 51 个历史 run 或 2,884 条聚合指标升级为 C1/C2/C3 的确认性证据；
- 不能从聚合指标反推不存在的逐 Query 候选、qrels 或关系标签；
- 不能把已曝光 Blind v4/v5 改名为 v6-GateA 或 v6-Blind；
- 不能未经逐集正文、许可、隐私、模型和内容 hash 校验就继承旧 token/向量。

因此它的准确表述是：**研究问题的经验起点与工程底座，不是确认性分母。**

> **概念解释｜假设来源与确认性证据**：假设来源说明“为什么值得研究”，允许来自既有观察；确认性证据用于判断假设是否成立，必须来自提前冻结、未被开发过程污染的数据。两者都重要，但证据等级不同。

## 3. 三个物理隔离 cohort

| cohort | 唯一角色 | 当前人口状态 | 当前访问状态 | 解锁条件 |
| --- | --- | --- | --- | --- |
| `internal-v6-dev` | 构念、标注、相似度、代理与功效校准 | 30 个结构合格提案完成双审；28 个接纳、2 个拒绝；接纳项已物化为版本化 Dev 摄取表；v5 三路证据已核验为 28 Query/112 Chunk/3,056 候选，三路各 28/28 非空，C2 8 槽补充仍为空 | 仅允许 Dev 开发与校准；不得迁移到 GateA/Blind | 使用 v5 开展 Dev 相似度与测量校准；另行生成并双审 C2 补充正文 |
| `internal-v6-gatea` | 独立 C1/C2 现象与代理研究 | 空 | 对方法开发锁定 | P2/P3/P4/P5 冻结、Gate A root hash 外部时间戳完成 |
| `internal-v6-blind` | Gate A=Go 后一次性 Gate B 确证 | 空 | curator/hash 工具之外全部锁定 | M1、比较器、\(\epsilon_{M1}\)、分析与 Gate B root hash 全冻结 |

划分单位固定为下列四者的组合组，而不是单个 Query 或 Chunk：

```text
query_family_id
× document_family_id
× version_family_id
× counterfactual_template_family_id
```

任一 family 在两个 cohort 间重合，两个受影响 cohort 都不能封存。重命名 ID、复制正文或改变 Chunk ordinal 不会消除 family 重合。

Blind 在填充后不向实验代码公开正文、数量或候选统计；M1 冻结前只有独立 curator 的只读资格/hash 工具可访问。当前 Blind 为空，所以 manifest 中的记录数采用 `null`，避免把未来人口规模变成方法开发信息。

## 4. 最小摄取 schema

### 4.1 Query 摄取

每条至少具有：

- Query 正文、稳定源 ID、SHA-256 与 `query_origin=natural/synthetic`；
- 采集来源、日期、用途授权/同意和隐私复核；
- `query_family_id`、关联文档/版本/template family；
- 历史曝光状态、建议 cohort、curator 和摄取状态。

`query_origin=natural` 只用于项目允许使用的实际信息需求、日志衍生的合规脱敏问题，或团队独立提出并确认代表真实任务的问题。LLM 生成的问题必须标为 `synthetic`，不得改名为 natural。

30-family v6-Dev 先导允许 DeepSeek 生成**受控合成微型事实世界**：每个 family 先生成稳定的 `synthetic_fact_id`、目标事实、目标证据、Query、等价对照、原子事实冲突和表面非冲突对照；目标真值只在该自包含微型语料内成立。模型标签只是提案，只有两名人工复核者确认目标组唯一、证据逐字可定位、关系与冲突原子性成立，并完成仲裁后，family 才能计为成功构造。该先导只估计合成构造流水线的可构造率，不估计自然候选产率，也不得复制到 GateA/Blind。

本轮首批 30 次调用成功返回 30 次，其中 24 个提案通过冻结的 JSON、逐字锚点、ID、来源和单次精确原子替换门禁，首批机械结构产率为 80%。6 条因默认思考模式占满输出额度而截断；四个后续恢复批次依次只读取上一批拒绝 ID，显式关闭思考模式、启用 JSON Output，并保留全部失败响应与独立 manifest，最终得到 30 个机械结构合格提案。总计 43 次调用、52,320 输入 token、190,663 输出 token，估算人民币 `0.934791` 元。该费用只含 API，不含人工工时。

恢复后的 30/30 不是人工接纳率。交付包固定为 `ROBUST-FUSION-INTERNAL-V6-HUMAN-REVIEW-2026-08-29-v1`：A/B 各完成 30 条案例资格、90 条候选和 90 条候选对，候选角色、冲突配额、模型标签和来源 ID 均对标注员盲化。六份提交于内容比较前完成独立快照锁定；机械错误与 unresolved 均为 0。候选级四字段及两个资格字段 100% 一致，候选对 89/90 一致；唯一分歧经主持人按适用条件规则裁定为 `factual_conflict`。

最终记录为 `ROBUST-FUSION-INTERNAL-V6-FACILITATOR-DECISION-2026-08-29-v1`：30 个结构提案中接纳 28 个、拒绝 2 个，人工接纳率为 93.33%。两个拒绝项的预设表面控制实际构成同事实槽的适用条件冲突；另有两个模型预设冲突类型被人工一致改判为 `numeric`。接纳后的主冲突类型为 numeric 9、version/time 8、negation/direction 7、applicability/condition 4。28 个主冲突的 `adjudicability` 全部为 `detectable_only`，所以本批可用于 Dev 冲突检测与压力构造校准，但不能单独覆盖 C2 的三分边界。

GateA/Blind 不接受“全 family 均由模型凭空生成且没有自然来源锚点”的记录。LLM 可以提出 Query 或反事实，但每个确认性 family 仍必须满足科研协议冻结的非零自然候选配额，具有独立、合规、可核验的自然来源证据，并与 v4/v5、Dev 及其他 cohort 的扩展 family 零重合。v5 只能提供已曝光的 prompt/schema 与成本经验，不能充当确认性来源锚点。

### 4.2 文档摄取

每条至少具有：

- 稳定 document/chunk ID、本地正文、内容 hash 和原文位置；
- 许可或内部使用授权、隐私复核；
- 文档 family、版本 ID、有效日期；
- parser、chunker、参数摘要和 source span；
- 历史曝光状态。

内部文档只允许一次性确定性切分。同一文档的新旧版本或相邻 Chunk 必须归入同一扩展 family，不能跨 Dev/GateA/Blind。

### 4.3 正确证据与关系层

每个 Query 至少要有经复核的目标证据，并另存：

- 来源 relevance 标签；
- `target_equivalence_group_id`；
- `target_relation`、`conflict_type`、`adjudicability`；
- 可复核的 evidence locator/span；
- 双人独立标注、仲裁状态和手册版本。

公开或历史数据中“未列为 relevant”不能自动变成负例。模型辅助预标注只用于筛选，不能替代人工确认事实等价、事实冲突或疑似漏标。受控合成微型事实的“正确”表示在冻结微型语料中的内部真值，不得被表述成经外部世界核证的自然事实。

## 5. 分享包资产资格表

本地包 `control/source_eligibility.tsv` 是机器可读台账，当前规则概括如下：

| 资产 | v6 可用角色 | 不可用角色 |
| --- | --- | --- |
| 分享包 + 旧 eval MySQL | 假设来源、工程 provenance、预算与可行性 | Query/qrel 真值或 Gate 结果 |
| `990123/990124` | 正文与来源验证后可作内部文档候选 | 验证前不能摄取 |
| `990126/990127` | 官方实体 ID/曝光 crosswalk | 乱码正文、旧向量、旧 token |
| `990131/990901/990997-990999` | 来源复核后的 Dev 诊断 | v6-GateA/v6-Blind |
| `991001-991004`、`992000-992003` | 正文/provenance 与 family 复核后，可作新 Query 的固定背景；历史 Query/标签仅 Dev | 历史 Query、目标身份或标签不能继承为确认性真值 |
| `993100-993104` | 动机、曝光登记、Dev 审计 | 永久排除 GateA/Blind |
| BM25/Alt/Qdrant | 契约完全匹配后的计算缓存 | 事实真值 |
| `ssh linkcv` | 中间件服务 | 数据或 qrels 来源 |

内部新增样本的最小工作量不是“重新标整个语料”，而是：

1. 新的、合规且显式记录 `query_origin` 的独立 Query family；
2. 每个 Query 的正确证据与扩展 document/version family；Dev 合成先导使用自包含 `synthetic_fact_id`，确认性 family 另须自然来源锚点；
3. 三路候选生成后的高相似等价、疑似冲突和疑似漏标项；
4. 只对这些高价值项做双人复核与仲裁。

这里允许复用的是固定语料背景，不是历史判断。只要正文/授权通过、历史 Query—目标—版本—template family 已排除，既有 corpus 可以降低重新建库成本；新 Query 的目标证据和候选关系仍必须独立建立。若某文档 family 曾直接参与相关方法训练、规则设计或人工构造，则它只能留在 Dev，不能借“背景语料”名义跨入 GateA/Blind。

最终 Query 数和 Dev/GateA/Blind 比例不在此处凭经验写死；它们必须由 P3-06 的可构造率先导和预注册功效分析在 Gate A 前冻结。

## 6. 生命周期与拒绝条件

正式人口流程固定为：

1. 摄取或生成新 Query、文档与目标证据，先记录 natural/synthetic 来源，再做许可、隐私、文本质量和目标真值检查；
2. 建立扩展 family，先与 v4/v5、分享包开发资产和三个 v6 cohort 做交集拒绝；
3. 只在 Dev 上校准标注、相似度、冲突代理、构造率和功效；
4. 按预先冻结的确定性规则整组分配 GateA/Blind，不按可构造效果或方法结果挑选；
5. 双人标注、仲裁、false-negative 审计和内容摘要完成后，分别生成 cohort root；
6. 按“资格快照 → root manifest → clean commit/tag → root SHA-256 → 外部时间戳 → receipt sidecar → 解锁”封存；
7. Gate A 运行只打开 GateA；Blind 保持关闭。只有 Gate A=Go 且 M1 全冻结后，Gate B 一次性打开 Blind。

出现下列任一情况即拒绝封存：

- 缺独立 Query family、正确证据、来源声明或所需用途授权；
- Dev 受控合成 family 未保存原始调用、`synthetic_fact_id`、逐字证据锚点或双人复核；
- GateA/Blind family 没有满足冻结配额的自然候选与独立自然来源锚点；
- 任一跨 cohort family 重合；
- 历史 Blind v4/v5 family 混入；
- 用公开未标注项自动补负例；
- 用聚合历史指标或旧向量冒充行级真值；
- Blind 在 M1 冻结前被实验代码扫描、计数或读取；
- 最终分母在查看 Gate 结果后修改。

## 7. 本地制品与复现命令

初始化脚本：

```bash
.venv/bin/python scripts/initialize_robust_fusion_internal_v6.py
```

生成、恢复与双人盲审包由以下两个入口复现；所有目标目录已存在时均拒绝覆盖：

```bash
.venv/bin/python scripts/run_robust_fusion_internal_v6_deepseek_pilot.py dry-run
.venv/bin/python scripts/run_robust_fusion_internal_v6_deepseek_pilot.py run --output runs/robust_fusion/internal_v6_deepseek_pilot_v2 --families 30 --temperature 0.7 --max-tokens 8192 --timeout-seconds 90 --concurrency 6 --max-retries 6
.venv/bin/python scripts/materialize_robust_fusion_internal_v6_human_review.py --output runs/robust_fusion/internal_v6_deepseek_pilot_v2_human_review_v1
.venv/bin/python scripts/review_robust_fusion_internal_v6_human.py lock
.venv/bin/python scripts/review_robust_fusion_internal_v6_human.py review
.venv/bin/python scripts/review_robust_fusion_internal_v6_human.py finalize
.venv/bin/python scripts/materialize_robust_fusion_internal_v6_adjudicated_dev.py
.venv/bin/python scripts/initialize_robust_fusion_c2_boundary_supplement.py
```

五段生成链的 manifest SHA-256 依次为 `c3efcbae1ee1a1ce0f33e2f135e24bc7710bb1973e86cbe390d4b9074b038f6b`、`7f067ca1d187026d2f0743d04c82278086e2a2642bc864919cd3378fc9a82a13`、`3896f8048c5b5e5112ec65de913b23928e107ebe790cf3e8b1a306c72c2acc74`、`070d26122417a7bd7a3bf008429abde1eca4723d5605553be92eed57044f848b`、`0d5d19ae204dfeeda4072577f6dca5ebf5345e5884cd460bacf601fd4300bf4f`；盲审交付 manifest SHA-256 为 `b5ad4ac4663e670be02e8e71eca5257e1106d420ac3153a8ac1fe155dd514db3`，提交锁 SHA-256 为 `72d8b77ca601c925ff3840afc4812ac1395019d1930548cd98836201adefbb00`，主持人最终 manifest SHA-256 为 `654ff9ff1959aeb18895b8a872c34665c9a262510f13d79146aca6183650b99a`。Dev 摄取 release 位于 `data/robust_fusion/internal_stress_v6/dev/releases/adjudicated_synthetic_v1/`，包含 28 条 Query、112 条单段文档、112 条证据标签和 28 条 family assignment；release manifest SHA-256 为 `ad32fbb08a6b076dced1e438ff51060c46073b932cd259ff89beb157e5453bac`，追加的 root manifest v9 SHA-256 为 `683e4967097e041a78fd7c5221c462ff4d75243127d8feb761cf7b0d40d7b2ab`。旧空 root/cohort manifest 没有覆盖。C2 空白补充包位于 `data/robust_fusion/internal_stress_v6/dev/supplements/c2_boundary_calibration_v1/`，固定 8 个规划槽且 0 个已物化案例，manifest SHA-256 为 `ff4e00d857641a2d48e0ece509c29bf357f28918757dc4a1980f9906a681f347`。

三路执行谱系不可覆盖：v1 零尝试 superseded；v2 plan SHA-256 `4e1e279b12e23436421b4b6166b261451000cd0e86817ada5d77ccd0cea98144` 因缺 SSH 转发而 transport 失败；v3 plan SHA-256 `14ee97c428b3a0ed460ff29cf2063e0cfd45c6d4969ebdac1d9d44feb5798818` 因本地 storage 父目录缺失而失败；v4 完成后因 manifest 纳入 SQLite 瞬态 sidecar 而拒收，原 manifest SHA-256 `d6e845e3311a4a08b6cebde9559109bbf2829b30df61a82783aec558604eef62` 保持不变。正式接纳的 Dev 制品是独立 v5：plan SHA-256 `a7b159cc7f8f2d694e816b820971a8d3bce85c2f1fe392dde5c4c0003df7c03a`，manifest SHA-256 `a2ee6147a791903fa0aceae3be7f3b6a7f54277a58f5241cb62d1e944974734d`，content root `1bae0b158a16f5d0aab161cff28245283fd487c9a5f41f23a6c4d02305c57550`。完整核验见[独立报告](../reports/internal_v6_dev_route_evidence_v5_verification_2026_08_29.md)。任何后续真实执行仍必须新建 run ID 与目录，重新准备计划并取得当次明确授权；不得重新执行 v2—v5 的既有计划。

在线 Dense/Sparse 现按 `ROBUST-FUSION-PROVIDER-ROUTE-SNAPSHOT-POLICY-2026-08-29-v2` 治理：不设数值误差或跨请求 exact 门槛；获授权运行只生成一次，结构合法后立即哈希封存，不因数值差异重跑或从多个运行中择优。v4/v5 数值差异只作描述，v5 的结构、覆盖和完整性结论保持有效，无需重跑。本地 BM25、文件摘要、指标和其他确定性计算仍须精确复现。

它只创建新目录；目标目录非空时拒绝覆盖。当前本地制品包括：

```text
data/robust_fusion/internal_stress_v6/
├── README.md
├── manifest.sha256
├── control/
│   ├── root_manifest.json
│   ├── source_eligibility.tsv
│   └── exposure_exclusions.tsv
├── intake/
│   ├── query_intake_template.tsv
│   ├── document_intake_template.tsv
│   ├── evidence_intake_template.tsv
│   └── family_assignment_template.tsv
├── dev/
│   ├── cohort_manifest.json
│   ├── releases/adjudicated_synthetic_v1/
│   └── supplements/c2_boundary_calibration_v1/
├── gatea/
│   ├── cohort_manifest.json
│   └── METHOD_ACCESS_LOCK.json
└── blind/
    ├── cohort_manifest.json
    └── METHOD_ACCESS_LOCK.json
```

该目录受 `.gitignore` 保护；版本库只保存本协议和生成器。以后任何人口变更都必须生成新 manifest/root hash，不得静默覆盖当前记录。

## 8. 完成判定

截至本记录：

| 层级 | 状态 | 说明 |
| --- | --- | --- |
| 数据集身份与用途 | 完成 | v6 唯一 ID、角色与排除边界已冻结 |
| 三分目录与访问锁 | 完成 | Dev/GateA/Blind 已独立建立 |
| 摄取 schema 与来源资格 | 完成 | 最小表和分享包资产边界已落盘 |
| Query/文档/证据人口 | 部分完成 | Dev 的 28 个双审仲裁接纳合成 family 已物化为 28 Query/112 文档/112 证据标签，2 个拒绝项未进入；GateA/Blind 仍无独立自然锚点人口 |
| family 分配与跨集零重合 | 部分完成 | 30 个 Dev 提案的四类 family ID 唯一、与本地 v5 的 23,852 个长度合格字符串精确全文 hash 重合为 0；语义近重复、确认性 cohort 分配仍未完成 |
| P2 双人标注校准 | 完成 | v2 保留 7 例 + v3 替换 5 例的合并准入通过，标注手册升级为 v2 |
| 30-family 生成、双审、仲裁与构造率 | 完成 | 首批机械结构产率 24/30；恢复后 30/30 完成 A/B 双审与主持人仲裁，人工接纳 28/30（93.33%） |
| Dev 三路检索证据 | 完成并独立核验 | v2/v3 失败和 v4 完整性拒收均保留；v5 完成 28 Query/112 Chunk/3,056 候选，三路各 28/28 非空，112/112 已标注候选和 28/28 gold target 入并集。manifest/content root、SQLite/FTS5 与真实 Qdrant 112 点核验通过；在线数值差异只作描述且不触发重跑；仍为 Dev-only、`NOT_ELIGIBLE`、`formal_p4_02_snapshot=false` |
| C2 三分边界补充 | 空白方案已冻结 | 8 个管理员规划槽已初始化，正文/答案键/人工标签均为 0；后续生成与 A/B 双审不改变 Gate 人口 |
| GateA/Blind 封存 | 未完成 | 依赖功效、P4/P5 和 root seal |

因此 P3-04 当前仍记录为“部分完成”：Dev 合成先导已完成，但 GateA/Blind 确认性人口仍为空；Gate A 仍为“未运行”。
