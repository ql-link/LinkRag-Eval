# #23 成员交付的官方 Test 聚合

2026-09-11 随 N=8 交付接收。此处保留 [results.json](results.json)、[frozen-config.json](frozen-config.json) 原件及 [原评价脚本](evaluate_official_test.py)。主口径 2,736 查询，E0／固定融合／N=8 严格正确为 1,549／1,431／1,492；只描述已收到的成员结果，不代表本机重新执行了 Test。

首次接收验证确认计数、比例、Wilson 区间和 McNemar p 值的算术一致；当时缺少原始候选、Test 查询／监督、逐题分数和运行日志，不能独立验证覆盖筛选、列表排名和一次执行时间线。后续快照补交后的核验范围见下文，旧接收记录保留其当时身份。完整范围见 [acceptance.json](../list-collapse-20260910/acceptance.json) 与 [正式报告](../../../docs/reports/list_collapse_2026_09_11.md)。逐查询 p 值没有处理同对／同来源依赖，不升级为已验证的来源组显著性结论。

成员台账还记载：首次聚合误把同分的确定性排序当作胜负，随后改为原始分数差，列表指标未变。该历史与原件保存在 [原始交付归档](../_handover/issue23-n8-delivery-20260911.tar.gz)，接收方未抹除。冻结 JSON 没有可核对的记录时间戳；其中融合特征版本写作 `candidate_difference_v3_english_v1`，实际脚本／模型契约使用 `candidate_difference_v3_en_v1`。原 JSON 不追改。

模型已恢复至 `../list-collapse-20260910/{baseline-disabled-replay,background-n8-training}/model-b/`。候选目录最初仅收到准备与采集脚本；2026-09-11 随后已补交 [完整本地快照与编码／采集记录](../nevir-test-candidates-20260910/README.md)。接收时为评价脚本增加已存在 results.json 就立即拒绝的护栏，防止覆盖原结果或误触发再次评分；原脚本字节保留在交付归档。没有执行 Test 下载、入库、采集或重新评分。

这份结果不包含当前主线 Qwen／GPT／BGE 的 Test 评价，不能据此将其他 issue 标为完成。补交后程序已验证 2,766 查询、2,738 共同覆盖和排除结构冲突后的 2,736 主分母，候选／监督正文及运行参数通过验收；该输入缺口已解决。成员逐题模型分数仍未交付，本次没有重放 E0／N=8，也没有补齐原事前冻结时间线；不能从聚合反推逐题结果或称 Test 完全未曝光。主线 Qwen／BGE 已完成的独立终评与中断恢复记录见 [#20 运行目录](../nevir-test-main-20260911/README.md)。
