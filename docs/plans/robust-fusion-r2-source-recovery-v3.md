# Robust Fusion R2 DeepSeek 正文来源 prompt-only 恢复规范 v3

> research_id: `ROBUST-FUSION-R2-2026-08-29`
> source_protocol_id: `ROBUST-FUSION-R2-SOURCE-RECOVERY-2026-08-29-v3`
> 状态：`AUTHORIZED_PROMPT_ONLY_RECOVERY_READY_TO_SEAL`
> v2 live root 与 24 次失败响应永久只读保留；v3 使用全新 preparation/live root。

## 1. 允许变化与不变边界

v2 失败被登记为 `PROMPT_CONTRACT_IMPLEMENTATION_FAILURE`：24/24 响应通过 JSON、exact keys 和六项 slot identity，但违反既有 parser 的四文本 normalized 两两唯一规则。这不是数据质量、measurement、编码器、人工审阅、readiness 或 Gate 结果。

v3 只修正文案契约。正式 scientific prereg、原 128 slots 及映射、44/42/42 与 12-cell 配额、四 conflict×四 edit×2、固定分母 128/256、冻结 parser、四文本 normalized 唯一性、R1 exact/template/5-gram 排除、S_qg(c) estimand、E5/DistilUSE 身份和全部人工/共同支持/measurement 门槛均不变。禁止程序化改写、补全或规范化 provider 输出。

## 2. 自包含 prompt contract

每次请求只发送固定 slot 元数据和以下抽象规则，不发送任何 v2 失败正文，也不提供会形成复用模板的实例：

- `query` 必须是问句，且 normalized 后不同于其余三个陈述字段；
- `reference` 是完整的全新虚构 microfact 陈述；
- `equivalent_candidate` 必须通过非事实性的同义替换或句法重排改写，normalized 后不得复制 `reference`，同时所有实体、数值、日期、版本、否定方向、适用条件和逻辑命题完全等价；
- `factual_conflict_candidate` 必须 normalized 后不同于其余三项，只改变冻结 `conflict_type` 指定的一个事实槽，其他事实保持不变；允许非事实性表面改写以满足 edit strength，但不得引入第二个事实冲突；
- 四个文本字段必须 normalized 后两两不同；响应前模型自行检查，但只输出 exact JSON object。

edit strength 对 reference→equivalent 和 reference→conflict 分别约束 normalized Levenshtein：level 1=`0.02–0.18`（局部同义替换/少量句法调整），level 2=`0.08–0.28`（短语级复述），level 3=`0.15–0.40`（明显句法重排），level 4=`0.22–0.58`（多处非事实性改写）。该说明只服务既有机械 parser，不构成新 estimand。

## 3. 执行、审计与停止

继续使用已授权的 DeepSeek base URL、`deepseek-v4-flash`、non-thinking、JSON mode；不设费用/token/总调用上限。每 slot 首个机械合格输出立即锁定，不按内容偏好、E5 或人工结果筛选。发送前/返回后 append-only JSONL + flush/fsync，所有失败响应保留。

v3 从固定 `R2SRC-001` 开始，不复用 v2 的任何 proposal。永久 provider 错误、安全边界、封存/身份/数据完整性漂移、连续 8 次 transport、连续 24 次同一新机械失败或同一响应 hash 六次触发非费用型硬阻塞。命令级 crash 后不得自动重启。

达到 128/128 后才执行冻结的 fixed denominator、R1 exact/template/5-gram、跨 R2 family near-duplicate 与配额校验并锁定正文；随后单次 E5/DistilUSE 和四份 A/B 人工包。模型输出仍为 proposal，不是真值。
