# #23 成员交付的官方 Test 聚合

2026-09-11 随 N=8 交付接收。此处保留 [results.json](results.json)、[frozen-config.json](frozen-config.json) 原件及 [原评价脚本](evaluate_official_test.py)。主口径 2,736 查询，E0／固定融合／N=8 严格正确为 1,549／1,431／1,492；只描述已收到的成员结果，不代表本机重新执行了 Test。

接收验证确认计数、比例、Wilson 区间和 McNemar p 值的算术一致；原始候选、Test 查询／监督、逐题分数和运行日志未交付，不能独立验证覆盖筛选、列表排名和一次执行时间线。完整范围见 [acceptance.json](../list-collapse-20260910/acceptance.json) 与 [正式报告](../../../docs/reports/list_collapse_2026_09_11.md)。逐查询 p 值没有处理同对／同来源依赖，不升级为已验证的来源组显著性结论。

成员台账还记载：首次聚合误把同分的确定性排序当作胜负，随后改为原始分数差，列表指标未变。该历史与原件保存在 [原始交付归档](../_handover/issue23-n8-delivery-20260911.tar.gz)，接收方未抹除。冻结 JSON 没有可核对的记录时间戳；其中融合特征版本写作 `candidate_difference_v3_english_v1`，实际脚本／模型契约使用 `candidate_difference_v3_en_v1`。原 JSON 不追改。

模型已恢复至 `../list-collapse-20260910/{baseline-disabled-replay,background-n8-training}/model-b/`。候选目录现仅收到 [准备与采集脚本](../nevir-test-candidates-20260910/README.md)，没有 snapshot。接收时为评价脚本增加已存在 results.json 就立即拒绝的护栏，防止覆盖原结果或误触发再次评分；原脚本字节保留在交付归档。没有执行 Test 下载、入库、采集或重新评分。

这份结果不包含当前主线 Qwen／GPT／BGE 的 Test 评价，不能据此将其他 issue 标为完成。后续需要该来源的成员提供原有候选与执行记录；不能从这份聚合反推逐题结果，也不能重新称这份 Test 完全未曝光。
