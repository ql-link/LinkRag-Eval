# 判断器统计

2026-09-11 #18 收尾：补 Qwen3-14B-AWQ 思考主方案与 BGE reranker v2-m3 在 K=20、融合破同分条件下的来源组统计。完整结果见 [tables.md](tables.md)，解释与限制见[报告 §11.1](../../../docs/reports/llm_judge_pilot_2026_09_10.md#open-statistics-20260911)。

Qwen 确认读取 `open-judge-confirmation-20260910/l2-first-pass-k20/`，保持 280/371，开发为 54/74；BGE 确认／开发为 257/371、47/74。四份额外输入均显式选 `stage1_judge`，各相对 E0 与固定融合，共新增 8 组比较；未计算 Qwen−BGE 的直接检验。Qwen 确认的四查询技术回退已包含在最终排序中，逐题关系无缺失不等于判断无失败。

确认 371 方向、96 来源组、185 完整配对；开发 74 方向、19 来源组、37 完整配对。确认材料已经曝光，开发只作描述性分析。额外排序器名称区分文件角色，某角色中 `matched=0` 的另一个角色文件只记录元数据，不生成比较。

基于 `23f465d` 加本地未提交修复运行，Git 状态与实际命令保存在 `results.json`。执行始于 2026-09-11 12:01:57 UTC，统计子进程墙钟 0.286 秒（含启动、写出，不含验收），退出 0；零模型／GPU 请求、训练或 Test 读取。原 12 组统计与 L3 来源记录精确复现；新增 8 组的身份、基线关系、分母、严格与双向区间、符号检验独立复算通过。35 项相关测试与完整非 integration 回归 1,299 passed、23 skipped、3 deselected、6 既存 warnings。

输入：/Users/kawauso/Documents/Projects/LinkRag-Eval/runs/post_recall/llm-judge-pilot-20260910 下的 L1/L2 官方逐题关系、L3 保存预测与报告，以及 L3 报告指定的基线、融合分数和基线 summary 指定的角色监督标签。具体路径与 L3 可派生状态见 results.json；未读取官方 Test 条目。

命令：
```sh
/Users/kawauso/Documents/Projects/LinkRag-Eval/.venv/bin/python /Users/kawauso/Documents/Projects/LinkRag-Eval/scripts/llm_judge_statistics.py run --root runs/post_recall/llm-judge-pilot-20260910 --out runs/post_recall/judge-statistics-20260911 --seed 20260910 --repeats 2000 --extra qwen_l2_confirmation:stage1_judge=runs/post_recall/open-judge-confirmation-20260910/l2-first-pass-k20/official-per-query.jsonl --extra qwen_l2_development:stage1_judge=runs/post_recall/open-judge-qwen3-14b-development-20260911/l2-k20/official-per-query.jsonl --extra bge_l2_confirmation:stage1_judge=runs/post_recall/open-judge-bge-reranker-v2-m3-20260911/confirmation-l2-k20/official-per-query.jsonl --extra bge_l2_development:stage1_judge=runs/post_recall/open-judge-bge-reranker-v2-m3-20260911/development-l2-k20/official-per-query.jsonl
```

种子 20260910，重采样 2000 次，95% 百分位区间。

开源判断器到位后复跑（输出目录必须不存在）：
```sh
.venv/bin/python scripts/llm_judge_statistics.py run --root /Users/kawauso/Documents/Projects/LinkRag-Eval/runs/post_recall/llm-judge-pilot-20260910 --out runs/post_recall/judge-statistics-open --seed 20260910 --repeats 2000 --extra open_judge=path/to/per-query.jsonl
```

--extra 名称[:关系列]=路径 可重复使用不同名称；显式列必须存在且关系有效。L2 用 --extra open_l2:stage1_judge=path/to/official-per-query.jsonl 读取融合破同分结果；选择 E0_judge 则读取 E0 破同分结果。未指定列时优先读取同名关系列，否则读取 judge 列。按 source_query_id 连接并自动分角色；可只提供一个角色或部分查询，缺项记 unavailable，无匹配角色不生成额外比较。重复 ID、身份冲突、域外查询和非法关系直接报错。额外排序器均相对 E0 和 stage1 比较。

差值为 a − b；pp 为百分点。严格正确仅指 strict_correct。CI 与符号检验均剔除任一排序器 unavailable 的行；双向指标剔除不完整或含缺失的配对。

CI 复用 N04 来源组有放回重采样，组内全部保留，按实际抽中行数计算微平均；少于两个来源组不报告区间。区间描述固定候选集合的组重采样稳定性。精确双侧符号检验以逐题不一致结果为单位，不校正组内相关性或多重比较。开发集已曝光，不作独立确认。

收尾：Ruff、报告索引与 `git diff --check` 通过。验收与本地未提交状态已写入 [issue #18](https://github.com/ql-link/LinkRag-Eval/issues/18)，2026-09-11 12:07:35 UTC 按 completed 关闭。
