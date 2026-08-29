# Robust Fusion R2 DeepSeek 正文来源三阶段恢复规范 v4

> research_id: `ROBUST-FUSION-R2-2026-08-29`
> source_protocol_id: `ROBUST-FUSION-R2-SOURCE-RECOVERY-2026-08-29-v4`
> 状态：`AUTHORIZED_RESULT_BEFORE_READY_TO_SEAL`
> 性质：source implementation recovery；不是 scientific prereg、数据结果、measurement 或 Gate 变更。

## 1. 继承与只读边界

v2/v3 的全部 provider 响应、append-only 账本、terminal/协调停止记录、机械诊断、报告及其 hash 永久保留。v4 使用独立 preparation、code snapshot、lock、receipt 和 live root；任何 v4 provider 响应前必须完成本地结果前 seal。v4 不覆盖、恢复或重放 v2/v3。

以下冻结项原样继承：scientific prereg；128 个固定 slot；44/42/42 dataset 配额；12 个 condition cell；每个 length×language 内 conflict 4 类×edit 4 级×2 family；候选固定分母 256；未修改 parser；四文本 NFKC/casefold/whitespace normalized 两两唯一；中文 normalized characters、英文 normalized words 的长度范围；四级 normalized-character Levenshtein edit bands；R1 exact/template/5-gram；已正式接受 R2 对象的跨槽 exact/template/5-gram；`S_qg(c)` estimand、E5/DistilUSE 角色和全部人工/共同支持/measurement 门槛。不得增样、换槽、降阈值或按结果选样。

## 2. R→E→C 三阶段

每个固定 slot 从一个新的 `orchestration_attempt` 开始，依次运行：

1. `R`：只生成 `query` 与 `reference`。prompt 明示冻结语言、长度单位/外界，并把 reference 目标放在合法区间内部：short-zh 60–90 chars、long-zh 220–300 chars、short-en 30–45 words、long-en 120–160 words。内部目标只是 prompt 引导，正式接受仍只用冻结外界。
2. `E`：只发送该 attempt 内刚由 DeepSeek 生成且机械锁定的 reference，生成 `equivalent_candidate`。必须命题等价、normalized 字符不同，只做非事实性同义替换或句法重排。prompt 同时给出冻结 ratio band、reference normalized 字符长度、等长候选时允许的 changed-character 整数区间和真实 parser 分母公式。
3. `C`：只发送同一 attempt 的 reference 与固定 conflict_type/edit_strength，生成 `factual_conflict_candidate`。只改变目标事实槽，其他事实保持不变；表面改写不得引入第二个事实变化。

后续阶段只接收完成该阶段所必需的同一 slot、同一 attempt 的 DeepSeek 新 synthetic reference；不发送 v2/v3 失败正文、R1、Blind、Gate、生产/内部正文、模型分数或人工结果。模型输出始终是待独立双人复核 proposal，不是真值。

程序只保存 provider 原字符串并确定性装配字段，禁止改写、扩写、截断、翻译、规范化修补或自动语义裁决。

## 3. 锁语义与排除

R/E/C 每阶段首个机械合格值只取得 `ATTEMPT_SCOPED_STAGE_LOCK`，不构成永久 slot 接受。R1 与已接受 R2 跨槽排除在字段可判时提前 fail-closed；四字段装配后仍须由原 parser 与全部 R1/跨槽门禁统一重验。

只有一个完整对象同时通过 exact schema、slot identity、语言/长度、四文本 normalized 唯一、两个 edit band、R1 exact/template/5-gram、已接受 R2 跨槽 near-duplicate 和固定机械门禁时，才将该 slot 的第一个完整合格对象永久接受。不得请求、保留或比较第二个完整合格对象。若只能在装配后判断的门禁失败，完整保留该 attempt，丢弃其 attempt-scoped 锁，再以相同固定 slot 开启下一版本化 attempt；不得替换 slot 或按措辞、E5、人工结果、construction role 择优。

## 4. 聚合无进展与运行安全

- 同一 slot、同一 stage 在当前 attempt 中累计 24 个完整 provider 响应仍未取得该阶段机械锁，命令级 fail-closed；失败类别交替也计数。
- 同一 slot 连续完成 24 个 R→E→C assembly attempt 仍无永久接受，命令级 fail-closed。
- 同一 slot/stage 相同 response hash 六次、连续八次 transport/429/5xx、永久 provider 错误、usage/envelope/schema 身份漂移、安全边界或封存漂移均立即停止。
- 费用和 token 不构成停止条件；逐调用成本仍记录。命令 crash/stop 后不得自动重跑。

每次请求发送前写 audit 并 flush+fsync；每次完整响应后写 response archive 和 audit 并 flush+fsync；每个 attempt-scoped stage lock、完整 assembly 和永久 proposal 分别写 append-only ledger。失败内容不删除。

## 5. 成功后的固定顺序

128/128 永久接受后，单次运行冻结的 `materialize_and_validate_families`，对 fixed denominator、44/42/42、12-cell、4×4×2、R1 与跨 R2 exact/template/5-gram 做统一复验并锁定正文。只有 data lock PASS 后才允许单次本地 E5/DistilUSE 和物理隔离的 relation A/B、similarity A/B 人工包；两名研究员每人 relation 256 + similarity 256 = 512 行。

人工提交前禁止 finalizer/readiness/Gate A/B；Blind、Reranker、D1–D3、A0/M1 继续禁止。不得 commit/push。
