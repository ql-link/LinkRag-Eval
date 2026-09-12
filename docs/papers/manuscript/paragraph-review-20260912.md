# 2026-09-12 成稿后的逐自然段独立复查

用户要求：写完第一批三项内容之后，调用独立 sub-agent，以自然段为单位复查。本记录由主任务根据复查者的逐段反馈及修订复核整理。

复查者为新建的 `paragraph_review_20260912` sub-agent，使用新上下文，未参与撰写，也不是前置材料核对任务的成员。范围为新增 S1–S5、M1–M6、D1–D4 共 15 个自然段，以及引言 I1–I6 的跨节一致性，共 **21 段**；表 1 与图 1 另核查。首次复查在三节正文写完后进行，修订后又由同一复查者核对必须项是否落实。

这是同一模型家族内、分离上下文的内部复查，不代表跨模型验证或正式会议审稿。复查者只读材料，没有改文件、运行实验或读取 Test 逐题文本、标签和分数。最终 PDF 图像检查由主任务执行。

## 逐段结果及处理

| 段落 | 复查结论 | 处理与关键证据 |
| --- | --- | --- |
| I1 | 可保留 | 条件辨别与列表位置动机一致。[NevIR](https://aclanthology.org/2024.eacl-long.139/) |
| I2 | 可保留 | 已承认 NevIR 及复现的训练取舍；100/101 为说明性例子，不是数据。[NevIR](https://aclanthology.org/2024.eacl-long.139/)、[复现论文](https://doi.org/10.1145/3726302.3730294) |
| I3 | 可保留 | 固定并集、共同覆盖、只评指定段与设置一致。[评价实现](../../../src/linkrag_eval/retrieval/learning_to_rank/llm_judge.py) |
| I4 | 可保留 | 确认计数、MRR 与联合干预限制一致。[列表聚合](../../../runs/post_recall/list-collapse-20260910/results.json) |
| I5 | 可保留 | Top20 逐段评分、融合破同分、尾部原序和组合收益边界准确。[排序实现](../../../src/linkrag_eval/retrieval/learning_to_rank/llm_judge.py) |
| I6 | 可保留 | 首次 280、BGE 257、复验 277、371 分母及确认曝光身份正确；未声明显著优于 BGE。[判断器报告 §10](../../reports/llm_judge_pilot_2026_09_10.md) |
| S1 | 可保留 | 同一候选池、路深度及编码器与历史采集一致；仅改善长模型名的断行。[数据与采集 §2](../../reports/nevir_same38_retraining_2026_09_07.md) |
| S2 | 需修改，已落实 | 明确 1,896 计划查询中 1,871 共同覆盖，再排除结构冲突的两方向，剩 1,869 入损失；补上归一化查询关联，避免把来源分组缩写为仅精确匹配。[数据记录](../../reports/nevir_same38_retraining_2026_09_07.md)、[分组代码](../../../src/linkrag_eval/runners/nevir_ltr_data.py) |
| S3 | 可保留 | 单查询严格偏好、185 完整对、ID 仅决定列表位置、条件 MRR 分开定义；没有误把并集覆盖改成 Top20 覆盖。[评价实现](../../../src/linkrag_eval/retrieval/learning_to_rank/llm_judge.py) |
| S4 | 需修改，已落实 | 人工 53/19/4 与严格共同覆盖 52、47 同向／5 反向准确；把“全部计划查询”成本分母限定于窗口重排，避免错误套用到 L1。[人工聚合](../../../runs/post_recall/subject-binding-pilot-20260908/human/adjudication/analysis-v2/results.json)、[输入构建](../../../src/linkrag_eval/retrieval/learning_to_rank/llm_judge.py) |
| S5 | 需修改，已落实 | 补明 Test 与早期划分四段精确正文重合被保留；保留技术纠错、成员原评分未交付；将瞬时关机／回收状态压缩为尚无完整核验的主线比较。[Test 接收范围](../../reports/list_collapse_2026_09_11.md)、[主线入口](../../../runs/post_recall/nevir-test-main-20260911/README.md) |
| M1 | 可保留 | 阈值过滤、log1p、分路 min–max、有效路权重归一化、常量路取 1 与代码相符；过滤融合贡献不改变已保存并集。[融合](../../../src/linkrag_eval/retrieval/tuning.py)、[特征入口](../../../src/linkrag_eval/retrieval/learning_to_rank/features.py) |
| M2 | 需修改，已落实 | 补 seed 20260907、最多 300 轮、patience 40、两臂 LambdaRank truncation level 2；英文适配的一次拟合与历史选参分开。[英文报告](../../reports/nevir_english_features_2026_09_07.md)、[训练实现](../../../src/linkrag_eval/retrieval/learning_to_rank/pairwise_training.py) |
| M3 | 需修改，已落实 | 给出 SHA-256 输入 `20260907:query-id`、前八字节、大端整数；保留无放回抽样及 2/1/0、gain 共同变化，不写单因素因果结论。[抽样实现](../../../src/linkrag_eval/retrieval/learning_to_rank/pairwise_training.py)、[N8 选择记录](../../../runs/post_recall/list-collapse-20260910/background-n8-training/selection.json) |
| M4 | 需修改，已落实 | 组合 head/tail 键仅用于成功评分；任一 head 缺分时同时恢复融合顺序及原始融合分用于严格比较。避免把回退后的跨窗口同分判成严格成功。[resort](../../../src/linkrag_eval/retrieval/learning_to_rank/llm_judge.py) |
| M5 | 需修改，已落实 | BGE 的原始连续 logit、FP16、336 tokens／无截断准确；把 6,144 输出上限限定于新请求及独立复验配置，不覆盖历史缓存。[BGE 配置](../../../runs/post_recall/open-judge-bge-reranker-v2-m3-20260911/execution-config.json)、[Qwen 开发记录](../../../runs/post_recall/open-judge-qwen3-14b-development-20260911/README.md) |
| M6 | 需修改，已落实 | 明说历史有效缓存可能来自较早输出上限；首轮缓存／重试、缺原冻结文件与复验空缓存／无重试均保留。复验不追认首次协议，也不被解释为仅改变失败策略的单因素比较。[首次](../../../runs/post_recall/open-judge-confirmation-20260910/README.md)、[复验](../../../runs/post_recall/open-judge-confirmation-20260911/README.md) |
| D1 | 可保留 | E0／融合严格偏好、MRR、均值排名与两段 Top10 均核对一致。[接收验收](../../../runs/post_recall/list-collapse-20260910/acceptance.json) |
| D2 | 可保留 | 保留 N8 相对 E0 少十条严格正确、相对融合 preferred@1 少一条；开发同向现象未当独立验证。[列表聚合](../../../runs/post_recall/list-collapse-20260910/results.json) |
| D3 | 可保留 | 本地复验范围有据；“consistent with”是解释性推断，未隔离机制，也未声称背景均不相关。[验收与范围](../../../runs/post_recall/list-collapse-20260910/acceptance.json) |
| D4 | 需修改，已落实 | 将错误分类／改写“remain necessary”改为“can test”，避免把两种暂定研究方案写成证明语义解释的必要条件。[当前研究状态](../../CURRENT_STATUS.md) |
| 表 1 | 表注需修改，已落实 | 数字不变；明确 Source groups 与 Used queries 同属入损失／共同覆盖的使用人群，Train 的 472 不是计划 473 来源组。[数据报告 §2](../../reports/nevir_same38_retraining_2026_09_07.md) |
| 图 1 | 可保留 | 三点严格比例与 MRR 与保存聚合一致；未伪造误差条。横轴补成 per-query，避免与双向全对混淆。[列表聚合](../../../runs/post_recall/list-collapse-20260910/results.json) |

## 修订复核与范围

复查者随后只读修订后的三个 `.tex`，确认九段文字与表注均已落实，未发现误改或首次复查必须项遗漏。引言的六段和实验数字没有因复查改变。所有主张仍受确认曝光、联合训练干预、背景无完整相关性标签及主线 Test 比较未齐的限制。

主任务另外核对图 1 坐标与原聚合、六个引用键、文档本地链接和 LaTeX 编译；这些属于文字／产物检查，没有新训练、推理或效果统计。完整正文未来合入主线 Test、成本和最终讨论后，还需针对新增内容复查；本记录不构成整篇论文已完成或投稿就绪的结论。
