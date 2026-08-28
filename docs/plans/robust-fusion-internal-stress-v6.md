# Internal Stress v6 数据协议

> 记录：`ROBUST-FUSION-INTERNAL-STRESS-2026-08-28-v6`
> 日期：2026-08-28
> 状态：数据身份、三分目录、访问锁、摄取 schema 与来源资格台账已正式建立；真实 Query/正确证据尚未摄取，当前不得进入 Gate A/B。
> 上位协议：[科研协议](robust-fusion-research.md)、[工程实施协议](robust-fusion-engineering.md)、[研究推进清单](robust-fusion-todo.md)。

## 1. 当前结论

Internal Stress v6 现在是一个正式、可核验的数据对象，而不再只是协议中的名称：

- 唯一记录为 `ROBUST-FUSION-INTERNAL-STRESS-2026-08-28-v6`；
- 本地忽略目录固定为 `data/robust_fusion/internal_stress_v6/`；
- `internal-v6-dev`、`internal-v6-gatea`、`internal-v6-blind` 分别有独立目录、manifest 与访问状态；
- 最小 Query、文档、证据和 family assignment 摄取表已建立；
- 分享包、SQLite 数据集、检索缓存、历史 Blind 和 `ssh linkcv` 的资格边界已经逐项登记；
- 全包由 `manifest.sha256` 校验，当前文件权限为目录 `0700`、文件 `0600`。

但“正式建立”不等于“已经有确认性样本”。分享包、本地工作 SQLite 和远端旧 eval MySQL 均为 `eval_query=0`、`eval_qrel=0`；服务器也没有另一份 LinkRag-Eval 行级包。因此 v6 当前状态固定为：

```text
FORMALLY_ESTABLISHED_AWAITING_NEW_REAL_QUERY_INTAKE
Gate eligibility: NOT_ELIGIBLE
```

在真实 Query、正确证据、family 隔离、双人复核、构造率与功效分母完成前，P3-04 只能记为“正式骨架完成、人口未完成”，不能标成全部完成。

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
| `internal-v6-dev` | 构念、标注、相似度、代理与功效校准 | 空 | 摄取并验证后可开发使用 | 完成来源、隐私、正确证据与 family 检查 |
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

- 本地真实 Query 正文、稳定源 ID 与 SHA-256；
- 采集来源、日期、用途授权/同意和隐私复核；
- `query_family_id`、关联文档/版本/template family；
- 历史曝光状态、建议 cohort、curator 和摄取状态。

“真实 Query”必须来自项目允许使用的实际信息需求、日志衍生的合规脱敏问题，或团队独立提出并确认代表真实任务的问题。为填满样本量而让模型批量虚构的问题只能标为 synthetic，不能替代非零真实来源要求。

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

公开或历史数据中“未列为 relevant”不能自动变成负例。模型辅助预标注只用于筛选，不能替代人工确认事实等价、事实冲突或疑似漏标。

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

内部确认性样本的最小新增量不是“重新标整个语料”，而是：

1. 新的、合规的真实 Query family；
2. 每个 Query 的正确证据与扩展 document/version family；
3. 三路候选生成后的高相似等价、疑似冲突和疑似漏标项；
4. 只对这些高价值项做双人复核与仲裁。

这里允许复用的是固定语料背景，不是历史判断。只要正文/授权通过、历史 Query—目标—版本—template family 已排除，既有 corpus 可以降低重新建库成本；新 Query 的目标证据和候选关系仍必须独立建立。若某文档 family 曾直接参与相关方法训练、规则设计或人工构造，则它只能留在 Dev，不能借“背景语料”名义跨入 GateA/Blind。

最终 Query 数和 Dev/GateA/Blind 比例不在此处凭经验写死；它们必须由 P3-06 的可构造率先导和预注册功效分析在 Gate A 前冻结。

## 6. 生命周期与拒绝条件

正式人口流程固定为：

1. 摄取新 Query、文档与目标证据，先做许可、隐私和文本质量检查；
2. 建立扩展 family，先与 v4/v5、分享包开发资产和三个 v6 cohort 做交集拒绝；
3. 只在 Dev 上校准标注、相似度、冲突代理、构造率和功效；
4. 按预先冻结的确定性规则整组分配 GateA/Blind，不按可构造效果或方法结果挑选；
5. 双人标注、仲裁、false-negative 审计和内容摘要完成后，分别生成 cohort root；
6. 按“资格快照 → root manifest → clean commit/tag → root SHA-256 → 外部时间戳 → receipt sidecar → 解锁”封存；
7. Gate A 运行只打开 GateA；Blind 保持关闭。只有 Gate A=Go 且 M1 全冻结后，Gate B 一次性打开 Blind。

出现下列任一情况即拒绝封存：

- 缺真实 Query、正确证据或用途授权；
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
├── dev/cohort_manifest.json
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
| 真实 Query/文档/证据人口 | 未完成 | 现有资产无 Query/qrel 行，不能伪造 |
| family 分配与跨集零重合 | 未完成 | 等人口后执行 |
| 双人标注、仲裁与构造率 | 未完成 | 依赖 P2 校准和真实候选 |
| GateA/Blind 封存 | 未完成 | 依赖功效、P4/P5 和 root seal |

因此 P3-04 当前应记录为“部分完成”，Gate A 仍为“未运行”。
