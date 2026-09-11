# 召回后实验产物导航

本页是 `runs/post_recall/` 的唯一导航。查实验先看状态列，再进目录 `README.md`。当前进度看[当前状态](../../docs/CURRENT_STATUS.md)，逐次实验看[实验台账](../../docs/experiments/EXPERIMENT_LOG.md)，数据划分看[数据入口](../../data/README.md)，模型身份看[模型入口](../../models/README.md)。本目录默认被 Git 忽略；各目录 README 及显式白名单中的轻量配置、聚合结果、复现脚本入库。原始运行数据、模型及缓存通常不随 clone 出现，具体范围见各目录说明。

## 1. 目录状态一览

| 状态 | 目录 | 内容 | 能否删除 |
| --- | --- | --- | --- |
| **共享输入，不可删** | [nevir-ltr-validation-20260907](nevir-ltr-validation-20260907/README.md) | Train／开发／确认的查询、监督与完整三路候选快照；所有英文实验都读它 | 否 |
| **当前结果** | [llm-judge-pilot-20260910](llm-judge-pilot-20260910/README.md) | N09：LLM 判断器三级试点，含判断缓存、评价与 L3 模型；正式报告见 [docs/reports](../../docs/reports/llm_judge_pilot_2026_09_10.md) | 否 |
| **交接证据与选型恢复** | [open-judge-selection-20260911](open-judge-selection-20260911/README.md) | #14–#16：原选择规则、执行时间线、运行资源证据与离线复验；事后恢复身份 | 否 |
| **当前开源补充结果** | [open-judge-qwen3-14b-development-20260911](open-judge-qwen3-14b-development-20260911/README.md) | N14／#15：Qwen 开发 L2 缓存补齐，固定配置、失败和 K10／K20 评价；主 K20 为 54/74 | 否 |
| **8B 开发 L2 补齐** | [open-judge-qwen3-8b-development-20260911](open-judge-qwen3-8b-development-20260911/README.md) | #15：运行前配置、全新缓存、1,520 项判断及 K10／K20 评价 | 否 |
| **当前文本参照** | [open-judge-bge-reranker-v2-m3-20260911](open-judge-bge-reranker-v2-m3-20260911/README.md) | N14／#15：BGE 固定权重对照，9,034 条判断、L1／L2 评价与脚本；主 K20 确认 257/371 | 否 |
| **开源确认结果** | [open-judge-confirmation-20260910](open-judge-confirmation-20260910/README.md) | N11／#16：首次与失败重试分列，实际配置及执行偏差 | 否 |
| **固定配置确认复验** | [open-judge-confirmation-20260911](open-judge-confirmation-20260911/README.md) | #16：已曝光确认上的单次请求复现，保留原 N11 并列对照；非新独立 Test | 否 |
| **当前成本分析** | [judge-cost-curve-20260910](judge-cost-curve-20260910/README.md)、[judge-cost-curve-qwen-20260911](judge-cost-curve-qwen-20260911/README.md) | N13／#17：GPT 一期与 Qwen 二期缓存曲线，分别保留触发规则的负／正结果及复验产物 | 否 |
| **小样本边界探针** | [ood-probe-20260910](ood-probe-20260910/README.md) | N10／#24：英文 6 查询与中文 12 对，原模型评分、中文完成复核表及离线复算；只作单段判断能力旁证 | 否 |
| **当前模型来源** | [nevir-english-features-20260907](nevir-english-features-20260907/README.md) | 英文基线由此训练；保存的开发全池分数是各实验的一致性校验基准 | 否 |
| **当前引用的人审与诊断** | [subject-binding-pilot-20260908](subject-binding-pilot-20260908/README.md) | N08：人审 v5 固定结果（`human/`）、五臂训练、v2/v3 修复产物 | `human/` 不可删；其余见 §3 |
| 同上 | [nevir-offline-diagnostic-20260907](nevir-offline-diagnostic-20260907/README.md) | 人审匿名映射 `review/private/`（人审 52 题评价必需）、旧 A/B 机械诊断 | `review/` 不可删；其余见 §3 |
| 同上 | [nevir-english-diagnostic-20260907](nevir-english-diagnostic-20260907/README.md) | 中文／英文基线在同一快照上的重放与追踪 | 见 §3 |
| 历史，保留不引用 | [nevir-controlled-20260907](nevir-controlled-20260907/) | 最初 20 对 NevIR 错排复现 | 否（问题存在性的原始证据） |
| 历史，保留不引用 | [nevir-suitability-20260907](nevir-suitability-20260907/)、[english-capability-20260907](english-capability-20260907/README.md) | 数据适用性审计、普通英文链路检查 | 否（小） |
| 历史，暂停 | [t2-full-20260906](t2-full-20260906/) | 暂停的 T2 入库及 `process-logs/` 故障记录 | 待定 |
| 归档 | [_archive](_archive/) | 早期连通性探针、Sparse 前缀探针、两份外部咨询提示词（ChatGPT Pro、Codex 统一执行稿） | 待定（小） |

## 2. 当前研究的文件依赖链

```
data/post_recall/nevir/{train,validation,test}.jsonl        原始划分（test 未读逐题）
  → nevir-ltr-validation-20260907/data-preparation/experiment/  prepared/ 与 candidates/（共享输入）
    → nevir-english-features-20260907/comparison/english/       英文基线与保存的开发分数
    → nevir-offline-diagnostic-20260907/review/private/         人审匿名映射
    → subject-binding-pilot-20260908/human/adjudication/        人审 v5 固定结果
      → llm-judge-pilot-20260910/                               N09 判断缓存、评价、L3 模型
```

新实验一律新建 `runs/post_recall/<目的>-<YYYYMMDD>/`，只读上面的输入，不改写它们；每个目录一份 `README.md`。

## 3. 归档结果与清理候选（2026-09-10 深度归档后）

被替代的中间版本、重复重放、大体量追踪和可重建环境已移入各实验目录的 `_superseded/`，每个目录有 `MANIFEST.md` 列出原路径、大小与原因；引用它们的报告链接已改指新位置。**未删除任何数据**，删除由负责人在 GitHub issue #27 决定。

| 目录 | 大小 | 内容 | 删除后果 |
| --- | ---: | --- | --- |
| `subject-binding-pilot-20260908/_superseded/` | 1.4 GB | 人审 intake-v1、ambiguity-policy-v1、analysis-v1、results-v1 到 v4；前三版分发包与审计快照；隔离 parser 环境副本；v2/v3 修复的全池重放、逐段事实 JSONL、三臂训练全池信号 | 人审最终版（v5、intake-v2）、模型包、结论文件全部保留；只失去中间过程的逐条复核能力 |
| `nevir-english-diagnostic-20260907/_superseded/` | 316 MB | 中文／英文基线逐树特征追踪与树路径核验明细 | 报告结论与 cases／summary 保留；重跑诊断脚本可再生成 |
| `nevir-offline-diagnostic-20260907/_superseded/` | 164 MB | 旧 A/B 特征追踪与树路径核验明细 | 同上；`review/private/` 人审映射保留原位 |
| `nevir-english-features-20260907/_superseded/` | 11 MB | 结构整理前的源码副本与 legacy 重放输入 | 结构一致性结论已在报告与 checks |
| `llm-judge-pilot-20260910/_superseded/` | 42 MB | 按 E0 前 10 名做的被替代设计、重复的续跑目录、工程会话空结果 | 无影响；判断缓存可被后续运行复用，删了只是重判 |
| `t2-full-20260906/` | 98 MB | 暂停的 T2 入库存储与故障日志 | 若研究不回到 T2，可整体删除 |
| `_archive/` | 0.7 MB | 早期探针与两份外部咨询稿 | 无影响 |

`runs/` 根目录的 `alt_embedding_eval.sqlite3`（95 MB）与 `bm25_eval.sqlite3`（117 MB）是[存放总览](../../docs/WORKSPACE_MAP.md)登记的评测库 sidecar，本次未动，是否仍在使用由负责人确认。

不在候选内、不可删：`nevir-ltr-validation-20260907/`（共享输入）、`subject-binding-pilot-20260908/human/`（人审最终结果与原始收件）、`nevir-offline-diagnostic-20260907/review/`（人审映射）、`nevir-english-features-20260907/comparison/`（英文模型与保存分数）、`llm-judge-pilot-20260910/` 下所有 `judge-cache/`、判断批次原始输出、`items-stage1-top20/`、`baseline/`。

## 4. 命名与文件约定

- 目录名写出数据集、目的与日期；不用 `new`、`final2`。
- `_archive/`、`_superseded/`、`_engineering-checks/` 三个前缀目录分别表示：不再引用的历史材料、被后续设计替代的结果、工程验收记录；它们都不进导航正文。
- `summary.json`／`results.json` 是所属命令的聚合统计，先看对应 README 的分母口径；`manifest.json` 在模型包内是契约、在运行目录内是范围记录。
- 大产物、缓存、模型继续忽略；新增需要入库的 README 时在 `.gitignore` 白名单补一行。


- 两期成本曲线均保存聚合 JSON、CSV、SVG、README 和复验记录；原始判断与候选从既有共享输入取得。二期仅离线重放，不把开发补齐的 GPU 成本省略为零成本。
