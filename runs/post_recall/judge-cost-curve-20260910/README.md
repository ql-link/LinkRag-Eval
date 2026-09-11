# 缓存判断成本与准确率曲线

实验 N13（issue #17 一期），2026-09-10。GPT-6 缓存重放已完成；开源模型曲线待开发与确认两集的 L2 缓存齐备后另跑。正式记录见[判断器报告 §12](../../../docs/reports/llm_judge_pilot_2026_09_10.md#12-缓存判断的成本曲线与触发条件n13issue-17)。

输入：`runs/post_recall/llm-judge-pilot-20260910` 下的英文 `baseline/<role>/scores.jsonl`、
`items-stage1-top20/<role>/stage1-<role>.jsonl`、`l2s-<role>-judge/scores.jsonl`；
三路来自 `runs/post_recall/nevir-ltr-validation-20260907/data-preparation/experiment/candidates/<role>/inputs.jsonl`，标签来自其同级 `prepared/<role>/supervision.jsonl`。
仅使用 validation 的 development、confirmation，不读取 NevIR 官方 Test。

```sh
.venv/bin/python scripts/llm_judge_cost_curve.py run --root runs/post_recall/llm-judge-pilot-20260910 --candidates runs/post_recall/nevir-ltr-validation-20260907/data-preparation/experiment/candidates --out runs/post_recall/judge-cost-curve-20260910
```

输出目录必须不存在。重跑开放模型缓存时添加 `--judge-dir-suffix=-<tag>`，选择
`l2s-<role>-judge-<tag>/scores.jsonl`，并将 `--out` 换成新目录；仍会独立核验原 GPT-6 K=20。

阈值只用开发集：扫融合前两名分差的 0–100% 分位数（步长 1%，linear），补充最大值的
下一个浮点数以覆盖严格 `<` 的全触发端点。固定 K=20，在严格正确数达到全 K 的 95%
的点中最小化平均有效判断数，成本相同取较小阈值。选定 `0.13015632331371307` 后直接用于确认集。
完整阈值扫描见 `margin-threshold-development.csv`；曲线、触发 CSV、SVG 与来源/参数见 `results.json`。

成本分母是全部查询（开发 76、确认 374），准确率分母是指定对共同召回的可评价查询
（开发 74、确认 371）。判断数按有效缓存候选计，缺失数和请求槽位另列；任一选中候选
未判断即按现有 `resort` 整条查询回退，已存在的判断仍计成本。K=1 也会重建分数，跨
窗口的原始平分可能被打破，因此严格指标不必与 never-call 完全相同。
触发比例表示调用条件成立，`changed_queries` 才表示实际改序。三路使用 `routes` 中
`rank=0` 的 chunk_id，`candidate_rows` 不是逐路排序。缺失/空路视为分歧并计数。

## 报告章节草稿

全调用 K=20 在开发集为 62/74 严格正确，在确认集为 311/371（83.83%）。分差触发在
开发集以 16.842 次平均判断达到 59/74，满足预设的 95% 保留标准；同一阈值在确认集
为 287/371，保留全调用正确数的 92.28%，平均判断 16.898 次，节省 15.51%。三路分歧
在确认集为 294/371，保留 94.53%，平均判断 17.326 次，节省 13.37%。因此这两种
触发规则在确认集均未保持全调用正确数的 95%，尚不足以支持该标准下的选择性调用收益。
描述性 K 曲线中，确认集 K=3 为 303/371、平均 3 次判断；这一观察不作为重新选 K 的确认性证据。
本次缓存缺失判断数为 0；开发/确认分别有 12/55 条查询存在空路，均按分歧触发。

本实验只重放已有判断，不产生新模型调用；成本是每查询候选判断数，不是 API 批次数、
实际 tokens、延迟或货币成本。开发集选择的阈值结果带选择偏差，确认集只报告固定阈值；
确认集 K 曲线为描述性对照，不据此再次选阈值。结果沿用官方偏好标签，不代表人工语义裁定。

K=20 self-check PASS (GPT-6 confirmation stage1_judge, all pairwise/list metrics): strict=311/371, both=129, pref@1=0.6495956873315364

confirmation

|K|strict|both|pref@1|mean judged|
|---|---|---|---|---|
|1|189|16|0.3666|1.000|
|2|238|59|0.5526|2.000|
|3|303|124|0.6334|3.000|
|5|306|126|0.6361|5.000|
|10|309|128|0.6442|10.000|
|15|310|128|0.6469|15.000|
|20|311|129|0.6496|20.000|

development

|variant|threshold|triggered fraction|mean judged|strict|both|pref@1|
|---|---|---|---|---|---|---|
|always_call|—|1.0000|20.000|62|28|0.6216|
|never_call|—|0.0000|0.000|38|3|0.3378|
|fusion_margin|0.13015632|0.8421|16.842|59|25|0.5676|
|route_disagreement|—|0.8289|16.579|60|25|0.5946|

confirmation

|variant|threshold|triggered fraction|mean judged|strict|both|pref@1|
|---|---|---|---|---|---|---|
|always_call|—|1.0000|20.000|311|129|0.6496|
|never_call|—|0.0000|0.000|189|16|0.3666|
|fusion_margin|0.13015632|0.8449|16.898|287|108|0.5903|
|route_disagreement|—|0.8663|17.326|294|113|0.6119|


## 接手复验与保存范围

原运行在基线 `da46a43` 加三个未跟踪实现文件上完成，根目录原始 CSV／SVG／`results.json` 保留。接手后在代码提交 `9174cbc` 上向 `recheck/` 重放，三组完整数值对象和七份 CSV／SVG 精确一致；实际复算耗时 **1.186 秒**（读输入、计算及原 K=20 校验，不含写产物）。[verification.json](verification.json)记录具体命令、来源、代码版本、时间和比对结果；`recheck/` 与渲染预览仅在本地保留。

新增来源校验：`scores.jsonl` 必须配有条数一致的 `summary.json`，每条记录与摘要的模型、推理强度、提示词一致；开发／确认必须是同一判断器，标签必须明确属于 validation 的对应角色。缺失候选仍按未判断计数；损坏文件、混合模型与缺失数据身份会明确报错。

验证：18 项成本曲线测试通过；完整非 integration 回归 **1,262 passed、23 skipped、3 deselected、6 warnings**。23 项跳过均为缺少真实 parser 运行环境，不称作 parser 验证通过；Ruff 与导入边界检查通过。两张 SVG 已渲染检查。

Git 保存本目录 README、聚合 JSON、CSV 与 SVG；逐条判断、候选正文和复验重复输出继续由已有本地运行目录保存。复现需取得上文所列共享输入；开源重跑需要两集对应缓存及各自 `summary.json`，不会由本脚本新增判断。

入库检查随后发现 CSV 默认 CRLF 被 `git diff --check` 判为行末空白；导出器和发布 CSV 已统一为 LF，数值不变。原 CRLF 复算输出仍在 `recheck/`，规范化说明见 `verification.json`。
