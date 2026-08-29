# Robust Fusion R2 source v7 与自动测量交接报告

日期：2026-08-29
research_id：`ROBUST-FUSION-R2-2026-08-29`
状态：`R2_AUTOMATIC_COMPLETE_AWAITING_FOUR_HUMAN_SUBMISSIONS`

## 1. Source data 收口

V7 按冻结 slot registry 顺序完成 R2SRC-001–128。R2SRC-001/002 逐字节继承并复验；R2SRC-003–128 为 Codex 直接撰写的 proposal，不是真值。全部 accepted row 都是对应 slot 的首个完整机械 PASS；失败稿、attempt hash 与审计账本均 append-only 保留。未使用外部生成服务，未在 128/128 前运行或查看 E5/DistilUSE。

Accepted ledger SHA-256 为 `c022a74eb273dc4b2d3f0e2f6232ec5824437e038b4c08783489c51a2b6a2ae8`。

旧 v7 `lock-data` 首次调用 fail-closed：它在正式 data root 创建前报 `within-R2 exact/template duplicate`。机械诊断得到 0 个 exact duplicate；16 个 template-signature 重复全部位于同一 family 内，主要是 numeric/version_time 的 equivalent/conflict 对，且包括硬继承 R2SRC-002。根因是最终执行器把同一 family 的四文本也加入所谓 cross-R2 累计，与冻结协议的 across-family/cross-slot 排除及配对设计不相容。这不是数据、measurement 或 Gate 结果。

独立 v7.1 erratum 在正式 data lock 前封存，只修复最终 duplicate-check 的作用域：当前 family 的四文本统一与所有先前 family 比较 exact/template/5-gram，但不在同一 family 内互相比 template/5-gram。原 v7、parser、accepted rows、proposal hashes、R1 registry、配额、edit bands、estimand 与全部门槛未变。v7.1 preparation manifest SHA-256 为 `363fda220711ebbdac6fef7033c85e48ac55d52c09dec08dea9aac95833971e9`。

正式 source lock 成功：128 families、256 candidates、44/42/42、12 cells 与 4×4×2 全部通过。关键哈希：

- data manifest：`547eacda8600a2c72d03f6c2c05d2c5ed0ac8ca4bc8427a1a6d1b9408cc17dc6`
- lock：`defdc1a8fa147bcbd67768266a5073bbc3e1096086a26d499a2736bd76fc8c07`
- families：`f41a9f76e78b8ab5a50df637e8512a3f34dc72ec08a768e70e4c75033c584231`

## 2. 唯一一次自动编码

Post-source-lock 自动执行规范、代码与测试先封存，preparation manifest SHA-256 为 `b0391cd94e9c83528629343b15a82a3309605b2a382532c263641288f35ef59b`。运行环境与资格环境一致：Python 3.11.15、sentence-transformers 5.7.0、Torch 2.13.0、Transformers 5.16.1、NumPy 2.4.6；CPU 单线程 deterministic。

唯一正式命令对 384 个锁定文本各运行一次 E5 主编码器与 DistilUSE 敏感性编码器，得到 `[384,768]` 与 `[384,512]` float32 向量。每个候选只与本 family 唯一 Clean reference 计算最大余弦；没有 Query—Candidate 分数、模型换位、候选替换或 score-based 删除。

E5 四个 length×language strata 均 0 截断。DistilUSE 的 short_zh/short_en 均 0 截断，long_zh 与 long_en 各 96/96 输入按冻结 128-token 右截断；这是预注册敏感性编码器的已知边界，不改变其角色。

关键自动制品 SHA-256：

- automatic manifest：`7b6c97e57e005a63bf530451a10ec5312c4f615ba13229e293dd428fcd22723c`
- computation config：`fa93b55099d879de41403eb90010956b945b407068117b8eb5014db87c19ee9e`
- candidate similarity：`6098c53b15d7f4115a31942cc45541739a10171d94ba5c9613820249099d926d`
- E5 vectors：`14d90db08756c1a4d93d2bb9acf7e78b1b5e41009d10b0495841ef37ca110e29`
- DistilUSE vectors：`37543fe43d46585b336aa26f4ea5622e84174b5a95585b9feac60930b9895eeb`

## 3. 人工包与唯一下一动作

四包均为物理独立目录，每包 256 行；annotator A/B 各需完成 relation 256 + similarity 256 = 512 行。包内只有 opaque audit_id、query/reference/candidate、冻结说明和空提交模板；没有 generator、construction role、候选角色、模型分数、分带或答案键。Facilitator registry 单独保存，SHA-256 为 `64b0469cb2857fad392ee1a58fabc1afacb1147855e8aaff9331d22b394114a0`。

- A relation：`runs/robust_fusion/r2_measurement_v1/robust-fusion-r2-measurement-v1-20260829/human_packages/relation/annotator_a/`
- A similarity：`runs/robust_fusion/r2_measurement_v1/robust-fusion-r2-measurement-v1-20260829/human_packages/similarity/annotator_a/`
- B relation：`runs/robust_fusion/r2_measurement_v1/robust-fusion-r2-measurement-v1-20260829/human_packages/relation/annotator_b/`
- B similarity：`runs/robust_fusion/r2_measurement_v1/robust-fusion-r2-measurement-v1-20260829/human_packages/similarity/annotator_b/`

每位研究员只进入自己的两个目录，阅读各自 `README.txt`，把 `submission_template.csv` 复制为 `submission.csv`，独立填写全部行，不改表头或 `audit_id`，也不查看另一位研究员或 facilitator 目录。当前四个 `submission.csv` 均不存在，Codex 未代填。

收到四份真实提交后，下一阶段必须先锁 hash 再解析、机械校验、比较和人工仲裁；此时才允许一次性 measurement finalizer。当前不得运行 readiness、Gate A/B、Blind、Reranker effects、D1–D3、A0 或 M1。
