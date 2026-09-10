# 判断器统计

输入：/Users/kawauso/Documents/Projects/LinkRag-Eval/runs/post_recall/llm-judge-pilot-20260910 下的 L1/L2 官方逐题关系、L3 保存预测与报告，以及 L3 报告指定的基线、融合分数和基线 summary 指定的角色监督标签。具体路径与 L3 可派生状态见 results.json；未读取官方 Test 条目。

命令：
```sh
/Users/kawauso/Documents/Projects/LinkRag-Eval/.venv/bin/python /Users/kawauso/Documents/Projects/LinkRag-Eval/scripts/llm_judge_statistics.py run --root runs/post_recall/llm-judge-pilot-20260910 --out runs/post_recall/judge-statistics-20260910 --seed 20260910 --repeats 2000
```

种子 20260910，重采样 2000 次，95% 百分位区间。

开源判断器到位后复跑（输出目录必须不存在）：
```sh
.venv/bin/python scripts/llm_judge_statistics.py run --root /Users/kawauso/Documents/Projects/LinkRag-Eval/runs/post_recall/llm-judge-pilot-20260910 --out runs/post_recall/judge-statistics-open --seed 20260910 --repeats 2000 --extra open_judge=path/to/per-query.jsonl
```

--extra 可重复使用不同名称；优先读取同名关系列，否则读取 judge 列。按 source_query_id 连接并自动分角色；可只提供一个角色或部分查询，缺项记 unavailable，无匹配角色不生成额外比较。重复 ID、身份冲突、域外查询和非法关系直接报错。额外排序器均相对 E0 和 stage1 比较。

差值为 a − b；pp 为百分点。严格正确仅指 strict_correct。CI 与符号检验均剔除任一排序器 unavailable 的行；双向指标剔除不完整或含缺失的配对。

CI 复用 N04 来源组有放回重采样，组内全部保留，按实际抽中行数计算微平均；少于两个来源组不报告区间。区间描述固定候选集合的组重采样稳定性。精确双侧符号检验以逐题不一致结果为单位，不校正组内相关性或多重比较。开发集已曝光，不作独立确认。
