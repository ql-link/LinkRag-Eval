# Robust Fusion R2 相似度 measurement 正式协议

> `record_id`: `ROBUST-FUSION-RESEARCH-R2-2026-08-29-v1`  
> measurement: `MATCHED_CALIPER_CONDITIONAL_E5_V1`  
> 状态：`RESULT_BEFORE_PROTOCOL_READY_FOR_LOCAL_SEAL`

数学 estimand 不变：`S_qg(c)=max_{h∈A_qg} cosine(z(c),z(h))`，其中 `A_qg` 只来自唯一目标等价组的 Clean evaluation view。它不是 Query—Chunk 相似度，也不是 M1 候选—近邻特征；construction role 不形成真值。

主编码器固定 `intfloat/multilingual-e5-base@d128750597153bb5987e10b1c3493a34e5a4502a`，512 tokens，`query:` 输入前缀、attention-mask mean pooling、L2 normalize、右侧截断；DistilUSE 固定 `sentence-transformers/distiluse-base-multilingual-cased-v2@bfe45d0732ca50787611c0fe107ba278c7f3f889`，128 tokens、右侧截断，只作敏感性。tokenizer 与模型同 exact revision；资格环境固定 sentence-transformers 5.7.0、Python 3.11.15、Torch 2.13.0、Transformers 5.16.1、NumPy 2.4.6、CPU 单线程与 deterministic algorithms。不得换位或模型赛马。

7 点量表：1=主题/实体/事件基本无关；2=仅宽泛主题或少量词面；3=同领域/实体但事件或谓词不同；4=同一事件框架但多个关键槽或语义关系不同；5=高度相似且有明显结构改写或一个关键槽差异；6=极高相似、近似复述或单一局部差异；7=命题等价、仅措辞/句法变化。relation 正确性另行标注。

早期草案的 caliper `>=5` 与“至少四个档位”数学冲突，因此在任何 R2 正文、分数或人工结果前修正为：family 两候选均 `>=4` 且差值 `<=1`。总体命中 ≥80%，四个 length×language 聚合各 ≥75%。这不改相关、共同支持或人工一致性门槛，也不增加工作量。

E5 在 12 个 dataset×length×language cell 内用 R2 Dev 样本均值/`ddof=1` 标准差条件标准化。每 dataset 独立计算 candidate-row Spearman/Kendall；每 family 固定两行，随后三 dataset 算术等权。bootstrap 在 12-cell 内按 family cluster 分层有放回抽样，每次重算标准化与 dataset 宏平均；正式 finalizer 固定 9,999 次、种子 2026082911，单侧 95% 下界取 5% 分位。

必要门禁：E5—人工 Spearman 点估计 ≥0.50 且单侧 95% 下界 >0.30；Kendall tau-b ≥0.35；四个 length×language 与两 relation 方向都 >0；leave-one-length×language-out 最大下降 ≤0.15。四个 length×language 聚合内分别用条件 E5 的 equivalent/conflict 观测范围交集计算共同支持，两侧覆盖都 ≥60%；12 个小 cell 逐项报告但不作同时极值必要门禁。每个 length×language 聚合至少四个评分档位且单档 ≤60%。similarity A/B QWK ≥0.60、within-one ≥90%；relation/similarity 的缺失、uncertain、无效、锁漂移均 fail-closed。

全部门禁 PASS 才进入 `R2_MEASUREMENT_PASS_AWAITING_READINESS`。点估计、Kendall、caliper 或共同支持低于门槛为 `R2_MEASUREMENT_FAIL_TERMINAL`；其余证据不足为 `R2_MEASUREMENT_INCONCLUSIVE_TERMINAL`。两者均无补样、无第二次 finalizer、无第三批、无阈值或 strata 修改。
