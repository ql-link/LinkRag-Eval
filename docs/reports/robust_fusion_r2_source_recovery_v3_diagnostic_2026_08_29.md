# Robust Fusion R2 source recovery v3 机械诊断

> research_id: `ROBUST-FUSION-R2-2026-08-29`
> 状态：`FAIL_CLOSED_SOURCE_IMPLEMENTATION_DIAGNOSTIC_AWAITING_V4_REVIEW`
> 本报告不评价正文语义，不形成数据质量、measurement、readiness 或 Gate 结果。

## 1. 结论

v3 已由协调方安全中断并原样封存：93 个完整 provider 响应、187 个审计事件、0/128 接受，另有一个发送前事件对应的在途请求在 SIGINT 时没有形成响应。没有自动重跑。失败是 prompt orchestration 不能同时让 provider 满足“reference 不复制”和 short-zh 最低长度，不是 parser 数学不可满足、阈值单位误用或 R1 冲突。

冻结 parser、scientific prereg、128-slot mapping、四文本 normalized 唯一性、R1 排除、estimand 与 measurement 门槛均未改变。v3 使用了 55,661 prompt tokens、12,880 completion tokens，peak 估算成本 `$0.04149244`。

## 2. 逐响应机械统计

诊断只输出 hash、字段长度与布尔/数值判定，不保存第二份正文。

| 检查 | 结果 |
| --- | ---: |
| 完整响应 | 93 |
| JSON object | 93/93 |
| exact keys | 93/93 |
| 六项 slot identity/type | 93/93 |
| 四字段语言判定 | 93/93 |
| R1 exact/template/5-gram 命中 | 0/93 |
| parser 首失败：四文本不唯一 | 69 |
| parser 首失败：长度 | 24 |
| 机械有效 | 0 |

69 个不唯一响应均为 `reference==equivalent_candidate`；没有放宽这一失败。其余 24 个响应四文本唯一，但都在长度门禁先失败。

short-zh 使用 parser 的 normalized 字符数，冻结范围为 reference/equivalent/conflict 各 35–130。实际分布：reference `16/21/36`、equivalent `15/21/36`、conflict `15/21/36`（min/median/max）；三个陈述字段各只有 1/93 达到长度范围。

reference→equivalent normalized Levenshtein 为 `0/0/0.4483`（min/median/max），23/93 落在 edit-level 1 的 `[0.02,0.18]`；reference→conflict 为 `0.0278/0.05/0.5357`，91/93 落入该区间。provider 因而稳定完成了 conflict 的局部变化，却主要在 equivalent 上选择完全复制；尝试非复制时又通常没有生成足够长的 short-zh 陈述。

## 3. 数学与单位核验

- 中文长度：prompt 和 parser 都使用 NFKC/casefold/空白归一后的字符数；一致。
- 英文长度：prompt 和 parser 都使用归一化空白分词数；一致。
- edit strength：prompt 和 parser 都使用 reference→candidate 的 normalized character Levenshtein ratio；四级区间一致。
- 本地构造的 128 个 slot 数值 witness 全部通过原 parser 的语言、长度、四文本唯一性与 edit band；v3 封存的全新 short-zh fixture 还通过真实 R1 exclusion registry。因此不存在机械阈值的数学不可满足。
- witness 只证明机械约束可满足，不替代人工语义真值；本诊断没有判断任何 provider proposal 是否真的 equivalent/conflict。

## 4. 最小 v4 建议：分阶段 prompt orchestration

不再要求单次响应同时发明四个字段。每个固定 slot 使用三个只按机械通过锁定的阶段，且不复用 v2/v3 失败正文：

1. `R` 阶段生成 query+reference，prompt 将长度目标放在冻结范围内部而非边缘；首个语言、长度和唯一性机械合格值立即锁定。
2. `E` 阶段只基于已锁 reference 生成 equivalent，明确所需 normalized 变更字符数区间；首个非复制、长度和 edit-band 合格值立即锁定。
3. `C` 阶段只基于同一 reference 生成 conflict，限定只改冻结事实槽并给出相同机械变更区间；首个机械合格值立即锁定。

程序只做字段的确定性装配，不改写任何模型字符串；装配后的完整对象仍由未修改的冻结 parser 和 R1/跨 family 排除器复验。每阶段不得因措辞偏好、E5 或人工结果换值。

为关闭 v3 的停止规则漏洞，建议新增聚合无进展 breaker：同一阶段累计 24 个 provider 响应仍没有锁定任何新字段时终止，不论失败类别是否交替；永久 provider、安全、封存和重复响应 breaker 继续保留。这是实施停止条件，不改变样本量或 estimand。

v4 必须使用新的 spec/code snapshot/preparation/live root，并在任何 v4 API 响应前封存。当前未启动 v4，等待协调方审核。

## 5. 制品

- v3 coordinator stop：`runs/robust_fusion/r2_source_recovery_v3/robust-fusion-r2-source-recovery-v3-20260829/coordinator_stop_decision.json`
- 逐响应机械诊断：`runs/robust_fusion/r2_source_recovery_v3_diagnostic_v1/robust-fusion-r2-source-recovery-v3-diagnostic-v1-20260829/per_response_mechanical_diagnostic.jsonl`，SHA-256 `11e19f39ea150587753404bc3ef4b281c649ad2aa6eb47ea057635954eefddfe`
- 诊断 summary：SHA-256 `8e9df39f0113b837c56935f198dde8c91f56bd0e3505dbf5f3554ea890cfa6f6`
- 诊断 manifest：SHA-256 `da2e9992c60a00bef92dc1f33ce60c7e571429ce18f8c8534d0bd910d5aaa790`
