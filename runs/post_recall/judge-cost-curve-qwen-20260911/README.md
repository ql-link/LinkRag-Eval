# 缓存判断成本与准确率曲线

输入：`runs/post_recall/llm-judge-pilot-20260910` 下的英文 `baseline/<role>/scores.jsonl`、
`items-stage1-top20/<role>/stage1-<role>.jsonl`、`l2s-<role>-judge-qwen3-14b-awq-think/scores.jsonl`
及对应 `summary.json`（核对条数与模型／推理强度／提示词，两集必须一致）；
三路来自 `runs/post_recall/nevir-ltr-validation-20260907/data-preparation/experiment/candidates/<role>/inputs.jsonl`，标签来自其同级 `prepared/<role>/supervision.jsonl`。
仅使用 validation 的 development、confirmation，不读取 NevIR 官方 Test。

```sh
.venv/bin/python scripts/llm_judge_cost_curve.py run --root runs/post_recall/llm-judge-pilot-20260910 --candidates runs/post_recall/nevir-ltr-validation-20260907/data-preparation/experiment/candidates --out runs/post_recall/judge-cost-curve-qwen-20260911 --judge-dir-suffix=-qwen3-14b-awq-think
```

输出目录必须不存在。重跑开放模型缓存时添加 `--judge-dir-suffix=-<tag>`，选择
`l2s-<role>-judge-<tag>/scores.jsonl`，并将 `--out` 换成新目录；仍会独立核验原 GPT-6 K=20。

阈值只用开发集：扫融合前两名分差的 0–100% 分位数（步长 1%，linear），补充最大值的
下一个浮点数以覆盖严格 `<` 的全触发端点。固定 K=20，在严格正确数达到全 K 的 95%
的点中最小化平均有效判断数，成本相同取较小阈值。选定 `0.19029679894447327` 后直接用于确认集。
完整阈值扫描见 `margin-threshold-development.csv`；曲线、触发 CSV、SVG 与来源/参数见 `results.json`。

成本分母是全部查询（开发 76、确认 374），准确率分母是指定对共同召回的可评价查询
（开发 74、确认 371）。判断数按有效缓存候选计，缺失数和请求槽位另列；任一选中候选
未判断即按现有 `resort` 整条查询回退，已存在的判断仍计成本。K=1 也会重建分数，跨
窗口的原始平分可能被打破，因此严格指标不必与 never-call 完全相同。
触发比例表示调用条件成立，`changed_queries` 才表示实际改序。三路使用 `routes` 中
`rank=0` 的 chunk_id，`candidate_rows` 不是逐路排序。缺失/空路视为分歧并计数。

## 报告章节草稿

本实验只重放已有判断，不产生新模型调用；成本是每查询候选判断数，不是 API 批次数、
实际 tokens、延迟或货币成本。开发集选择的阈值结果带选择偏差，确认集只报告固定阈值；
确认集 K 曲线为描述性对照，不据此再次选阈值。结果沿用官方偏好标签，不代表人工语义裁定。

K=20 self-check PASS (GPT-6 confirmation stage1_judge, all pairwise/list metrics): strict=311/371, both=129, pref@1=0.6495956873315364

confirmation

|K|strict|both|pref@1|mean judged|
|---|---|---|---|---|
|1|189|16|0.3666|0.995|
|2|227|52|0.5148|1.995|
|3|274|101|0.5472|2.992|
|5|277|103|0.5526|4.989|
|10|277|104|0.5580|9.989|
|15|277|104|0.5580|14.989|
|20|280|106|0.5580|19.989|

development

|variant|threshold|triggered fraction|mean judged|strict|both|pref@1|
|---|---|---|---|---|---|---|
|always_call|—|1.0000|19.974|54|20|0.5135|
|never_call|—|0.0000|0.000|38|3|0.3378|
|fusion_margin|0.1902968|0.9211|18.395|52|18|0.4865|
|route_disagreement|—|0.8289|16.553|54|19|0.5135|

confirmation

|variant|threshold|triggered fraction|mean judged|strict|both|pref@1|
|---|---|---|---|---|---|---|
|always_call|—|1.0000|19.989|280|106|0.5580|
|never_call|—|0.0000|0.000|189|16|0.3666|
|fusion_margin|0.1902968|0.9545|19.080|275|101|0.5472|
|route_disagreement|—|0.8663|17.318|267|93|0.5337|

## 本轮身份与复验

2026-09-11 开源二期，只重放 Qwen 缓存；新开发推理属于 N14，见[输入记录](../open-judge-qwen3-14b-development-20260911/README.md)。开发／确认分别保留 2／4 条不可用评分与整查询回退。K20 全指标已与 N14 开发和 N11 确认独立对照，重复计算的 curves、triggers、selection 和七份 CSV／SVG 均精确相同，见 [verification.json](verification.json)。`recheck/` 为本地忽略的复算副本。

分差与三路分歧在确认分别保持全调用正确数的 98.21%、95.36%，达到既定 95% 计数标准；仅为已曝光集合上的描述性结果。这里统计的是有效缓存判断数，未覆盖失败尝试的真实推理成本。实证解释见[报告 §12.4](../../../docs/reports/llm_judge_pilot_2026_09_10.md#qwen-cost-20260911)。
