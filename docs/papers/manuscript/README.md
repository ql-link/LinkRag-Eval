# 论文工作稿：引言、设置、方法与列表诊断

9 月 11 日已写英文 Introduction；9 月 12 日按用户指定的第一批任务补齐场景／数据／指标、对照方法与两种干预、列表诊断及必要限制。未启动新实验或完整写作流水线。[main.tex](main.tex) 组合当前工作稿，题名暂定，作者和摘要尚未加入。研究进度仍以 [CURRENT_STATUS.md](../../CURRENT_STATUS.md) 为准，本文件记录写作证据及编译方法，不维护另一套进度。

唯一论文 PDF 为 [paper.pdf](paper.pdf)，主入口为 [main.tex](main.tex)。后续继续编辑现有章节源码并覆盖生成 `paper.pdf`，不另存引言预览、日期版或其他稿件 PDF。LaTeX、BibTeX、PDF、[Makefile](Makefile) 和写作说明均纳入 Git，历史版本通过 Git 追溯；编译辅助文件留在被忽略的 `build/`。旧引言预览和旧工作稿 PDF 已清理。正式 Test 已有[核验报告](../../reports/nevir_official_test_2026_09_12.md)，本稿尚未整合其结果章节。

| 正文编辑入口 | 本批用途 | 自然段编号（源码注释，不进入 PDF） |
| --- | --- | --- |
| [introduction.tex](introduction.tex) | 研究问题与贡献边界 | 按出现顺序 I1–I6 |
| [experimental_setup.tex](experimental_setup.tex) | 固定场景、数据使用、指标和证据身份 | S1–S5 |
| [methods.tex](methods.tex) | E0、N=8、固定融合、BGE、Qwen | M1–M6 |
| [list_diagnostics.tex](list_diagnostics.tex) | RQ1 已验证结果及图 1 | D1–D4 |

新增三节以同一确认分母下的证据为主；图 1 直接使用已保存聚合，未新算模型效果、置信区间或训练结果。总稿仍为六页以内的阶段性工作稿，RQ2 主线 Test 结果、完整成本比较、Related Work、Abstract 和最终结论未在本批补写。

成稿后由未参与撰写、使用新上下文的 sub-agent 对 21 个自然段及表／图逐一复查，并在修改后完成针对性复核。九段文字及表注的澄清已落实，实验数字不变；逐项意见、证据和处理见 [逐段复查记录](paragraph-review-20260912.md)。

当前编译结果为 **3 页 IEEE 双栏**，含六条参考文献；TeXcount 统计正文约 2,051 词，其中本批新增三节约 1,570 词。已逐页检查最终渲染，图表坐标与原聚合一致，引用均已解析，无文字溢出。此页数是当前工作稿的实际占用，不代表尚未写入的内容可以不受六页总限额约束。

## 本版的论证选择

主线是：**同一固定混合候选池内，成对偏好和指定段落的位置是不同的评价目标；训练干预与受限组合重排对两者的影响需要分别验证。** 不以“第一次发现否定辨别与一般排序存在取舍”为贡献，也不声称提出新的 LLM 重排范式。

六段分别回答：

1. 为什么“找到同主题内容”还不足以满足查询条件？为什么既看相对偏好，也看列表位置？
2. NevIR 和复现研究已经回答什么？本项目进一步追问的同池问题是什么？第 100/101 名只是解释指标的假设例子，不是实验数据。
3. 固定候选的边界、评价对象和覆盖条件是什么？为什么指定段位置不能代表全池相关性？
4. 成对训练及背景候选训练揭示了什么分离现象？为什么不能把联合干预写成已证明的单一机制？
5. 如何在既有范式下引入有限窗口的逐段判断？为什么结果属于窗口、模型分数和融合破同分的组合？
6. 当前确认结果支持什么范围？首次与复验有什么区别？哪些推广性结论尚不成立？

本版最后一段保留确认集身份及首次 280 / 复验 277 的区别，属于实验未收尾时可审阅的引言。主线 Test 完成后，需要重新决定最后一段的结果预告与贡献强度；不能只替换数字却继续沿用不成立的解释。

## 15 篇 short paper 的引言学习记录

已阅读 collection `Short Papers — 写作参考` 中 15 篇的 Introduction，并核对相关边界。它们提供写法参照，不意味着要把 15 篇全部引用到正文。ACL/NAACL 附录及其他会议的页数政策也不能替代本论文的六页总限额。

| 范文与正式入口 | 对本版有用的写法 | 不迁移的结论或设置 |
| --- | --- | --- |
| [LLM-based Query Expansion Fails for Unfamiliar and Ambiguous Queries](https://doi.org/10.1145/3726302.3730222) | 用明确条件限定负结果，避免写项目流水账 | 不把某类查询的失败外推为普遍失效 |
| [Beyond Yes and No](https://aclanthology.org/2024.naacl-short.31/) | 围绕一个可检验的评分设计选择展开 | 其标签概率评分不同于本项目生成离散分数并用融合破同分 |
| [Call for Rigor in Reporting Quality of Instruction Tuning Data](https://aclanthology.org/2025.acl-short.9/) | 区分测量结果与能力解释 | 不据此宣布 NevIR 指标无效 |
| [Limited-Resource Adapters Are Regularizers, Not Linguists](https://aclanthology.org/2025.acl-short.19/) | 把反直觉结果和对照放到论证中心 | 本项目尚无同等程度的机制隔离 |
| [Measuring Hypothesis Testing Errors in the Evaluation of Retrieval Systems](https://doi.org/10.1145/3726302.3730229) | 说明一个评价判断为什么需要检验其前提 | 不宣称本项目提出新统计检验 |
| [Dwell in the Beginning](https://aclanthology.org/2024.acl-short.35/) | 从具体观察收束到可控制的评价问题 | 文档内部位置与候选列表排名不是同一变量 |
| [Paraphrasing in Affirmative Terms Improves Negation Understanding](https://aclanthology.org/2024.acl-short.55/) | 尽早定义语言现象，再提出简单干预 | 肯定式释义改变文本；不能提前充当本项目改写探针的证据 |
| [Enhancing Retrieval Systems with Inference-Time Logical Reasoning](https://aclanthology.org/2025.acl-short.34/) | 把复杂条件具体化为可检验变量 | 子查询编码超出本项目固定候选重排边界 |
| [Zero-Shot Cross-Lingual Reranking with Large Language Models for Low-Resource Languages](https://aclanthology.org/2024.acl-short.59/) | 承认重排范式已有，说明新场景中的实证增量 | 不把应用既有范式写成发明方法 |
| [Context-Efficient Retrieval with Factual Decomposition](https://aclanthology.org/2025.naacl-short.16/) | 成本必须绑定明确单位 | 候选判断数、tokens、延迟不能互换；其文档表示也不同 |
| [CORD](https://aclanthology.org/2025.naacl-short.66/) | 用两个合理目标之间的张力组织全文 | 生成器的位置偏置不等于本项目指定段列表位置 |
| [A Human-AI Comparative Analysis of Prompt Sensitivity in LLM-Based Relevance Judgment](https://doi.org/10.1145/3726302.3730159) | 分开提示、模型和输出方案的作用 | 标注可靠性不直接等于重排质量；本地附件为作者 arXiv 稿 |
| [LLMs instead of Human Judges?](https://aclanthology.org/2025.acl-short.20/) | 将有效性限定到具体任务与评价条件 | 不推论 LLM 普遍替代人工标签 |
| [KnowShiftQA](https://aclanthology.org/2025.acl-short.16/) | 精确定义何种文本证据应改变答案 | 尚未执行的改写探针不能证明模型使用了指定证据 |
| [DocFinQA](https://aclanthology.org/2024.acl-short.42/) | 保留原任务核心、改变信息环境，再检查原能力判断 | 固定召回并集仍不等于完整语料或端到端 RAG 评价 |

最直接影响结构的是 DocFinQA 的评价环境扩展、CORD 的双目标张力，以及跨语言重排论文对既有范式的准确定位。当前引言实际引用只有 NevIR、Reproducing NevIR 和 Beyond Yes and No：前两篇约束研究缺口，后一篇支持逐段 LLM 排序属于已有方法范畴。

## 关键主张的证据与返工条件

| 引言内容 | 当前证据入口 | 本版边界／后续影响 |
| --- | --- | --- |
| 固定三路并集、Top20、逐段 0–4 判断、融合破同分、窗口外原序和整题回退 | [现行研究计划 §1.3](../../plans/post-recall-research-plan.md)、[实际排序代码](../../../src/linkrag_eval/retrieval/learning_to_rank/llm_judge.py) | 方法事实可以稳定描述。LLM 不看官方配对信息；最终效果属于组合规则。正式 Methods 再写模型 revision、thinking、提示和请求参数。 |
| 偏好改善与列表位置退化同时出现 | [列表诊断报告](../../reports/list_collapse_2026_09_11.md) | 确认 371 题：E0 208 正确、首选 MRR .3169；融合 189、.6017。E0 同分按失败计，不能用 chunk ID 排序算严格胜负。不是全池相关性质量。 |
| 背景训练恢复位置却不提升相对 E0 的偏好 | [同一报告的背景候选部分](../../reports/list_collapse_2026_09_11.md) | N=8：198 正确、首选 MRR .6133。标签层级、增益和背景采样共同变化，背景未人工判为不相关；单臂、单种子不能隔离机制。 |
| Qwen 组合的确认收益 | [判断器报告 §10.4、10.5](../../reports/llm_judge_pilot_2026_09_10.md) | 首次 Qwen 280/371，融合 189，BGE 同窗 257；首选 MRR .7265 对 .6017。另一指定段平均位置由 3.70 变为 4.55，不能概括为两个指定段均改善。 |
| 首次与复验分开保留 | [判断器报告 §10.6、10.8](../../reports/llm_judge_pilot_2026_09_10.md) | 新固定配置复验 277/371，7/374 查询回退；确认集已经使用，不是独立 Test。原首次缺少冻结 JSON，发生过失败补试；新复验不追认旧流程。 |
| 组合收益不等于单独语义能力更强 | [判断器报告 §10.5、10.7](../../reports/llm_judge_pilot_2026_09_10.md) | BGE 单独 L1 为 261/371，高于 Qwen 首次 211；8B 后补开发 L2 也略高于固定 14B。不写 Qwen 单段判断最好或 14B 全局最优。 |
| 统计分母与稳定性 | [判断器报告 §11.1](../../reports/llm_judge_pilot_2026_09_10.md) | 374 计划查询中 371 共同覆盖，185 完整配对、96 来源组。主偏好是单查询严格正确，不是 NevIR 双向全对；排序规则同分不因 ID 确定顺序就算正确。现有来源组区间不能替代独立 Test，也不据此声称 Qwen 显著优于 BGE。 |
| 人工标签的不确定性 | [人工复核报告 §2.8](../../reports/nevir_subject_binding_pilot_2026_09_08.md) | 开发人工严格可判且共同覆盖为 52，其中 47 与官方一致、5 相反；平局和未决保留。引言写 designated/preferred passage 而非无争议的真相关段，完整限制后续必须披露。 |
| Test 的实际使用历史 | [列表报告的接收与补交说明](../../reports/list_collapse_2026_09_11.md)、[主线 Test 运行入口](../../../runs/post_recall/nevir-test-main-20260911/README.md) | N=8/E0/融合 Test 已有成员聚合，输入已补交核验，成员逐题模型分数仍缺，四段已知跨划分正文重合保留。主线 Test 已执行，但写作截止时尚无完整核验的 Qwen/BGE 比较；具体恢复和接续进度看运行入口，不在论文跟踪实例瞬时状态。 |
| 错误类型、改写与成本 | [当前状态](../../CURRENT_STATUS.md)、[判断器报告 §12](../../reports/llm_judge_pilot_2026_09_10.md) | 选定错误集不代表总体分布；模型预标不等于完成的人审；改写未有正式结果。调用数下降只是代理成本，不能据此宣布同等比例 tokens、时延或费用节约。均未在引言预写正结果。 |

如果 Qwen 主线 Test 不优于同窗 BGE，应删除任何优越性定位，把重排写成有限条件下的比较；若仅优于融合，仍可报告既有文本重排对该场景的作用。如果 Test 不复现确认收益，最后一段应转向确认结果的局限。成对训练与列表位置分离的已验证确认事实仍成立，但不能继续概括为跨划分普遍规律。错误分析或改写出现负结果，主要收窄语义解释；它们不会抹去既有排序数值。

## 六页总预算与后续写作顺序

[IEEE BigData 2026 Undergraduate and REU Consortium](https://bigdataieee.org/BigData2026/undergraduate-reu-consortium/) 明确最多六页，包含图、表及参考文献。IEEEtran 预览用于现在检验双栏密度，并不等于已完成最终投稿模板、作者资格与版式核对。当前预览含暂定题名、四节、表 1、图 1 和六条引用，不补空白章节来凑六页。

| 内容 | 预算（页） |
| --- | ---: |
| 题名、作者、摘要、关键词 | 0.35 |
| Introduction | 0.85 |
| Related work | 0.35 |
| 固定候选设置与指标定义 | 0.80 |
| 重排方法 | 0.55 |
| 结果及核心图表 | 1.60 |
| 讨论、限制、结论 | 0.55 |
| References | 0.95 |
| **合计** | **6.00** |

本批已经落实设置、方法和列表诊断三个任务。最终结果预告、Abstract 和 Conclusion 等主线 Test 后再定。历史 A/B、规则抽取失败、GPT 参照、L3 与触发成本曲线不预设全部进入正文，按是否帮助解释核心对照取舍。当前较详细的执行历史用于保证工作稿身份清楚；最终合稿时可压缩到限制与产物说明，但不能删除首次／复验、已曝光集合或技术纠错事实。

编译（在本目录运行）：

```sh
make
```

编译成功后，`Makefile` 将 PDF 移至固定路径 `paper.pdf`，`build/` 只保留辅助文件；编译失败时保留上一次成功生成的 `paper.pdf`。从仓库根目录也可运行 `make -C docs/papers/manuscript`。

引用条目取自 ACL Anthology 正式 BibTeX、已核验 DOI 的 Zotero 会议记录、NeurIPS 论文入口、Qwen3 技术报告和 BAAI 官方模型卡。不把范文摘要、模型预标或旧讨论稿当作本项目的实验结论。

## 本批正文的实现与证据入口

| 自然段 | 主要依据 |
| --- | --- |
| S1–S2 | [历史采集与数据划分报告 §2](../../reports/nevir_same38_retraining_2026_09_07.md)、[实际数据准备记录](../../../runs/post_recall/nevir-ltr-validation-20260907/data-preparation/preparation.md)、[来源分组代码](../../../src/linkrag_eval/runners/nevir_ltr_data.py) |
| S3–S4 | [严格／双向／列表评价实现](../../../src/linkrag_eval/retrieval/learning_to_rank/llm_judge.py)、[人工 v5 记录](../../reports/nevir_subject_binding_pilot_2026_09_08.md)、[成本单位实现](../../../src/linkrag_eval/retrieval/learning_to_rank/judge_cost_curve.py) |
| S5 | [成员 Test 接收说明](../../../runs/post_recall/nevir-test-final-20260911/README.md)、[主线 Test 当前记录](../../../runs/post_recall/nevir-test-main-20260911/README.md) |
| M1 | [融合变换和归一化](../../../src/linkrag_eval/retrieval/tuning.py)、[baseline_score 的阈值调用](../../../src/linkrag_eval/retrieval/learning_to_rank/features.py) |
| M2–M3 | [英文 E0 报告](../../reports/nevir_english_features_2026_09_07.md)、[完整 c3 参数和运行产物](../../../runs/post_recall/nevir-english-features-20260907/comparison/comparison.json)、[N8 选择记录](../../../runs/post_recall/list-collapse-20260910/background-n8-training/selection.json)、[训练实现](../../../src/linkrag_eval/retrieval/learning_to_rank/pairwise_training.py) |
| M4–M5 | [提示及排序／回退代码](../../../src/linkrag_eval/retrieval/learning_to_rank/llm_judge.py)、[BGE 执行配置](../../../runs/post_recall/open-judge-bge-reranker-v2-m3-20260911/execution-config.json)、[BGE 接口](../../../runs/post_recall/open-judge-bge-reranker-v2-m3-20260911/run_bge.py)、[Qwen 开发配置](../../../runs/post_recall/open-judge-qwen3-14b-development-20260911/execution-config.json) |
| M6 | [选模与后补比较](../../reports/open_judge_selection_2026_09_11.md)、[首次确认与缓存／重试](../../../runs/post_recall/open-judge-confirmation-20260910/README.md)、[固定配置复验](../../../runs/post_recall/open-judge-confirmation-20260911/README.md) |
| D1–D4、图 1 | [列表诊断报告](../../reports/list_collapse_2026_09_11.md)、[原聚合 results.json](../../../runs/post_recall/list-collapse-20260910/results.json)、[接收复验 acceptance.json](../../../runs/post_recall/list-collapse-20260910/acceptance.json) |

为避免正文堆实现细节，以下参数由上表产物承载：E0/N8 的 `colsample_bytree=.8`、`min_child_samples=20`、最多 300 轮、patience 40、seed 20260907、单线程、`lambdarank_norm=true`，两臂 `lambdarank_truncation_level` 都为 2。38 列中的逐路归一化特征在原路结果上计算；融合分的归一化在阈值过滤后计算，两者不可混用。

Qwen revision 为 `31c69efc29464b6bb0aee1398b5a7b50a99340c3`，BGE revision 为 `953dc6f6f85a1b2dbfca4c34a2796e7dde08d41e`。Qwen 的生成请求 seed 为 null，批次打乱 seed 不能写成固定生成随机种子；原首次 revision 的事后核实不冒充事前冻结。NevIR 下载 revision 为 `6263585072ce3b435ed09658613553fbf4e74184`，该版本原 Train 即 948 对，仅 Validation 在项目中重划。
