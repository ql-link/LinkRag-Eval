# Robust Fusion R2 人工提交锁定与仲裁前审阅报告

## Material Passport

- Material ID: `ROBUST-FUSION-R2-HUMAN-REVIEW-PRE-ADJUDICATION-2026-08-29-v1`
- Material type: Human-study validation report
- Research ID: `ROBUST-FUSION-R2-2026-08-29`
- Verification status: `ANALYZED`
- Workflow status: `AWAITING_HUMAN_ADJUDICATION`
- Gate status: `NOT_AUTHORIZED`

## 1. 先锁后验

协调方只确认四份 `submission.csv` 的存在性、大小和 mtime，未读取内容。正式审阅的第一项研究动作只读取原始字节并锁定 SHA-256、路径、大小、mtime_ns 与对应 package manifest；没有解析 CSV 或比较 A/B。

submission lock 位于：

`runs/robust_fusion/r2_measurement_v1/robust-fusion-r2-measurement-v1-20260829/human_review/submission_lock_v1/`

- `lock.json`: `679bf8d1c187fc5701788d202c83df298fe6296fd35f56673118b380c79f952a`
- relation A: `eb15ac0b26435ff1204cc83ed3cd8f2d6f9c2aafc4c34f5be8145d36882845b2`, 14,853 bytes
- relation B: `0ad7cb1427031b4415566f86b5d3daf65a6c2aaeb246732772120bb6b61e1c4b`, 14,290 bytes
- similarity A: `122bb9ee6c55ed342c80f3df4091cd480f89b59dc85f334becbcde8aa842edf9`, 8,059 bytes
- similarity B: `99c43b2cf0905c09e3901940c674de3aaa4ea6ced776edc7309b005acd6a30fc`, 6,956 bytes

四个盲包 manifest 分别与冻结值 `457b4ed5…a6b97`、`c3cb8060…993d7`、`719bb5c4…17b4`、`61fbb82f…9a82` 完全一致。

## 2. 锁后执行器

仓库此前没有 R2 人工提交的正式审阅/finalizer 入口。该缺口被记录为冻结协议的缺失执行实现，不是 protocol、estimand、分母、编码器、统计口径或门槛变更。解析真实答案前，独立封存 spec、代码、CLI 与不使用真实结果的合成测试：

- spec: [docs/plans/robust-fusion-r2-human-review-finalization-v1.md](https://github.com/ql-link/LinkRag-Eval/blob/50f3a9b0ead581fb17fc3e4080c70361c9f24475/docs/plans/robust-fusion-r2-human-review-finalization-v1.md)
- preparation manifest: `94fd5cafe6e0d23dbef3884eea45f97eaff171d3441cf4e6b7e5d9aa2ad08e77`
- preparation receipt: `eab99acea6a32b18940fbcaccf759f783877f961eb4f3531f5b23dbdd9cb4b02`
- seal 明确 `submission_answers_parsed_by_seal=false`
- 封存前 Ruff PASS；合成目标测试 8/8 PASS

## 3. 机械验证与一致性

四份提交均通过 exact header、各 256 行固定分母、无缺失/重复/额外 audit ID、A/B 物理身份隔离、允许枚举、relation 条件约束、uncertain note 约束、package/registry/automatic/source/prereg hash 漂移检查。研究员文件没有被修改、规范化或替换。

relation：

- `valid_reference`: 256/256 A/B 一致
- `unique_target_group`: 256/256 一致
- `target_relation`: 253/256 一致
- `conflict_type`: 251/256 一致
- 四字段共同完全一致：251/256
- frozen 规则下需人类仲裁：7；其中含 uncertain：4

similarity：

- 精确相同分数：166/256
- 相差不超过 1：245/256，95.703125%
- quadratic weighted kappa：0.7457966253546364
- 一致性门槛（QWK ≥0.60、within-one ≥90%）：PASS
- frozen 规则仍要求任何非零差异或 uncertain 取得唯一人类终审值，因此需仲裁：96；其中含 uncertain：8

两任务共 103 个仲裁行、100 个唯一候选；3 个候选同时需要 relation 与 similarity 仲裁。pre-adjudication manifest 为 `eb536cadca6c22505dcef22f9bb62984137bd040f215e600f44eb4b2dad9573a`，receipt 为 `82dfeca974f7d3d7728e6ff2f8835d3cb5218f0aba30343445d77be6c1af870e`。

## 4. 人类仲裁包

物理隔离根目录：

`runs/robust_fusion/r2_measurement_v1/robust-fusion-r2-measurement-v1-20260829/human_review/adjudication_v1/`

relation 包位于 `relation/`，7 行：

- `cases.csv`: `93fd8a49f2fa7783d408c212946510000e7f92c4498318c4dc73b138d75bca2f`
- `submission_template.csv`: `7c39553e438315f8a6a439552933a8aef9fa6d4b32b4e395f3a2fc43d1876d24`
- `package_manifest.json`: `ca19585816683534ea86402f6f7a0f5e13f0ec4f6f5a8734df26797ea94bf46d`

similarity 包位于 `similarity/`，96 行：

- `cases.csv`: `f72a19007bc2229baa1892e5943a7959e9016b159f303359fe0978032d982cfe`
- `submission_template.csv`: `a798e20128d6cde0e2e162e5f9b67244ea3c7354038c7e22763f6e688c33d76e`
- `package_manifest.json`: `c974c90408a499069995139cc0df75aa77a97b54c1c81541562c3d89106e9411`

总仲裁 manifest 为 `bd7d8c6d5d7a44f002b21828e8200a67fa7c52b1a60f373087ee16f06e5b4a32`，receipt 为 `75b31919d45d5955ca3bd76ae293b1bf8090e2a3f5f9b970025f72e8fa48083f`。包内没有自动模型分数、生成器身份、construction role、答案键或期望方向；Codex/模型/工具未填写仲裁答案。

## 5. 当前决定与唯一下一动作

当前不是 measurement PASS/FAIL/INCONCLUSIVE，而是 `AWAITING_HUMAN_ADJUDICATION`。正式 finalizer、readiness、Gate A/B、Blind、Reranker、D1–D3、A0 与 M1 均未运行。

一名真实人类仲裁员分别只打开 `relation/` 和 `similarity/`，阅读各自 `README.txt` 与 `cases.csv`，把同目录 `submission_template.csv` 复制为 `submission.csv` 并填写全部 7/96 行；不得改表头或 `adjudication_id`，不得查看 facilitator registry、自动分数、生成来源或 construction role。完成后通知主持人；下一阶段必须先锁这两份仲裁提交的原始字节，再解析与执行唯一 finalizer。

## 6. 工程验证

- R2 human-review + measurement + automatic 目标测试：18/18 PASS
- 全量非 integration：531 PASS、3 deselected
- import-lint：183 files、902 dependencies、0 broken
- Ruff、`git diff --check`、报告索引检查：PASS
- 全量测试第一次以 `PYTHONPATH=src` 调用时，12 个依赖仓库根目录 `scripts` 包的测试在 collection 阶段报 `ModuleNotFoundError`；没有执行测试或研究计算。随后透明改为项目所需的 `PYTHONPATH=src:.`，单次完整执行得到上述 531 PASS。该命令环境修正不涉及研究输入、答案、门槛或结果重跑。
