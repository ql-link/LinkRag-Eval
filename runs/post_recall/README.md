# 召回后实验产物导航

本页是 `runs/post_recall/` 的唯一导航。查实验先看状态列，再进目录 `README.md`。当前进度看[当前状态](../../docs/CURRENT_STATUS.md)，逐次实验看[实验台账](../../docs/experiments/EXPERIMENT_LOG.md)，数据划分看[数据入口](../../data/README.md)，模型身份看[模型入口](../../models/README.md)。本目录整体被 Git 忽略，只有各目录的 `README.md` 入库；运行数据不随 clone 出现。

## 1. 目录状态一览

| 状态 | 目录 | 内容 | 能否删除 |
| --- | --- | --- | --- |
| **共享输入，不可删** | [nevir-ltr-validation-20260907](nevir-ltr-validation-20260907/README.md) | Train／开发／确认的查询、监督与完整三路候选快照；所有英文实验都读它 | 否 |
| **当前结果** | [llm-judge-pilot-20260910](llm-judge-pilot-20260910/README.md) | N09：LLM 判断器三级试点，含判断缓存、评价与 L3 模型；正式报告见 [docs/reports](../../docs/reports/llm_judge_pilot_2026_09_10.md) | 否 |
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

## 3. 清理候选（未删除，等负责人批准）

以下目录不影响当前结论的复现，但删除不可逆，本次只登记：

| 目录 | 大小 | 说明 |
| --- | ---: | --- |
| `subject-binding-pilot-20260908/representation-v3-20260909/` 中的逐段事实 JSONL 与 `source-at-fit/` | 约 810 MB 中的大部分 | v3 抽取的详细记录；报告与模型已保留结论，重算入口在 README |
| `subject-binding-pilot-20260908/repair-20260909/` | 421 MB | v2 修复的全池重放输出 |
| `subject-binding-pilot-20260908/environment/` | 110 MB | 隔离 parser 环境的安装副本，可按 README 重建 |
| `nevir-english-diagnostic-20260907/diagnostic/` 中的追踪文件 | 约 318 MB | 树路径追踪；诊断结论已在报告 |
| `nevir-offline-diagnostic-20260907/feature-traces.jsonl` | 149 MB | 旧 A/B 特征追踪；`review/` 必须保留 |
| `llm-judge-pilot-20260910/_superseded/` | 42 MB | 按 E0 前 10 名做的被替代设计、重复的续跑目录 |
| `t2-full-20260906/` | 98 MB | T2 暂停；若研究范围不再回到 T2 可整体删除 |

不在候选内的：所有 `judge-cache/` 与判断批次原始输出（它们是判断可复现性的凭据）、`items-stage1-top20/`（第一阶段分数与条目）、`baseline/`（英文基线全池分数）。

## 4. 命名与文件约定

- 目录名写出数据集、目的与日期；不用 `new`、`final2`。
- `_archive/`、`_superseded/`、`_engineering-checks/` 三个前缀目录分别表示：不再引用的历史材料、被后续设计替代的结果、工程验收记录；它们都不进导航正文。
- `summary.json`／`results.json` 是所属命令的聚合统计，先看对应 README 的分母口径；`manifest.json` 在模型包内是契约、在运行目录内是范围记录。
- 大产物、缓存、模型继续忽略；新增需要入库的 README 时在 `.gitignore` 白名单补一行。
