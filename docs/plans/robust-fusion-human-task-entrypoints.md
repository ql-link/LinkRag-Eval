# 鲁棒融合研究：人工作业浅入口规范

> 记录：`ROBUST-FUSION-HUMAN-TASK-ENTRYPOINTS-2026-08-30-v1`
> 适用范围：本研究后续所有需要研究员、仲裁员、curator、研究负责人或独立审稿人直接接触文件的任务。
> 核心原则：**深层目录只服务机器追溯，浅层入口只服务人工作业。**

## 1. 为什么需要单独的人工作业层

`runs/robust_fusion/...` 同时编码研究主题、阶段、版本、run ID、日期、角色和证据类型，适合不可变制品、哈希和 manifest 追溯，却不适合作为人工操作界面。让研究员直接进入这类目录会产生三类风险：

1. 路径过长，容易进入相邻版本、错误角色或 facilitator 目录；
2. 操作说明被机器内部命名淹没，初次参与者难以判断应该读什么、填写什么；
3. 为了“方便”而复制包时，容易出现两份 `submission.csv`、提交漂移或锁错文件。

因此，本研究把机器证据层与人工作业层明确分开。

```text
runs/robust_fusion/...       # 机器权威层：深、版本化、可哈希、通常 gitignored
human_tasks/<task-id>/       # 人工作业层：浅、按角色隔离、只暴露必要文件
```

## 2. 强制规则

1. 任何需要人类填写、复核、仲裁、签署或独立审阅的任务，在交付前都必须建立项目根目录相对的浅入口：`human_tasks/<task-id>/`。
2. 人工说明中的入口目录最多两层：`human_tasks/<task-id>/`；实际文件最多再增加一层工作区，例如 `human_tasks/r2-adjudication/relation/cases.csv`。
3. 给研究员的 `START_HERE.html`、README、聊天指令和交接消息不得要求其识别 `runs/`、`data/`、run ID、日期目录或 facilitator 路径。
4. 同一任务的不同角色必须拆成不同 `task-id`；例如未来双审使用 `gatea-review-a` 与 `gatea-review-b`，不得让 A/B 从同一个入口自行选择子目录。
5. 项目内协作优先使用目录符号链接，让人工输出直接写入唯一权威包；禁止为了缩短路径而复制一份可编辑包。
6. 若任务需要离开当前项目目录传递，必须生成独立导出包和明确的回收/导入步骤；不得把依赖符号链接的目录直接压缩后外发。
7. 每个入口必须只有一个 `START_HERE.html`，并明确：任务目标、允许查看的文件、需要生成的文件、行数、禁止事项、完成后的通知方式。
8. 人工提交仍遵守“先锁后读”：浅入口只是操作界面，不改变 canonical 文件、提交哈希、manifest、固定分母或仲裁协议。
9. 人工入口不得暴露模型分数、预期关系、construction role、配额目标、其他研究员答案、facilitator key、Gate 结果或 Blind 结果。
10. 未通过浅入口校验的人工包只能记为“机器已生成”，不得记为“可交付给研究员”。

## 3. 当前 R2 的正式人工作业入口

当前新仲裁员只需要进入：

```text
human_tasks/r2-adjudication/
├── START_HERE.html
├── relation/
└── similarity/
```

实际操作路径固定为：

```text
human_tasks/r2-adjudication/START_HERE.html
human_tasks/r2-adjudication/relation/cases.csv
human_tasks/r2-adjudication/relation/submission.csv
human_tasks/r2-adjudication/similarity/cases.csv
human_tasks/r2-adjudication/similarity/submission.csv
```

`relation/` 与 `similarity/` 是指向冻结 R2 仲裁包的相对符号链接。它们不是副本；研究员在浅入口内保存的 `submission.csv` 就是主持人之后要锁定的权威提交。

## 4. 剩余研究流程的人类接触点

| 阶段 | 人类角色与任务 | 计划浅入口 | 交付前必须满足 |
| --- | --- | --- | --- |
| R2 当前阶段 | 新研究员完成 relation 7 行与 similarity 96 行独立仲裁 | `human_tasks/r2-adjudication/` | 当前已建立；入口校验通过后交付 |
| C2 Dev 边界补充 | A/B 独立复核 8 槽正文、关系与可识别性；分歧由第三人仲裁 | `human_tasks/c2-review-a/`、`c2-review-b/`、`c2-adjudication/` | 正文、答案隔离、角色盲化和固定行数先锁定 |
| Gate A 候选资格 | 主复核者确认正确证据、等价组、事实关系、冲突类型与可裁决性 | `human_tasks/gatea-review-a/` | Gate A 样本量、候选上限、数据集分母和手册版本先冻结 |
| Gate A 双审与漏标审计 | 第二人复核最高相似带、全部等价对照、全部分歧和疑似 false negative | `human_tasks/gatea-review-b/` | 第二人只能看到自己的盲包；不得看到 A 的答案或方法结果 |
| Gate A 仲裁 | 独立仲裁员处理 A/B 分歧和 uncertain | `human_tasks/gatea-adjudication/` | A/B 提交必须先锁后比，仲裁包只含必要上下文 |
| Gate A 准入签署 | 研究负责人核对资格、预算、功效、root hash 与时间戳，不看确认性排序结果 | `human_tasks/gatea-readiness-signoff/` | 只暴露清单、摘要和签署回执，不暴露 Gate 结果 |
| Gate A 唯一追加（条件性） | 仅在预注册 Inconclusive 且负责人批准时完成新增样本复核 | `human_tasks/gatea-supplement-review-*/` | 新增范围、上限、合并规则和停止点必须先封存；不得复用原任务目录 |
| Gate B Blind 资格 | 独立 curator 完成自然来源、冲突真值、family 隔离和封存复核 | curator 独立工作区内的 `human_tasks/gateb-curator-*/` | 主方法工作区不可见；主仓只记录不泄漏正文/数量的 opaque ID 与 hash |
| Gate B 解锁签署 | 负责人在 M1 和全部比较器冻结后核对 Blind seal 与一次性运行清单 | `human_tasks/gateb-readiness-signoff/` | 只暴露 seal、commit、hash、receipt 和运行清单，不提前暴露正文或统计 |
| P9 论文独立评审 | 独立审稿人审阅主张、统计、局限和材料完整性 | `human_tasks/manuscript-review-<round>-<reviewer>/` | 每位审稿人独立入口；评审意见与作者回复分开保存 |

纯机器步骤——候选快照生成、Reranker 运行、bootstrap、Gate 统计和指标报告生成——不创建人工入口。只有需要人类实际读写文件时才建立入口，避免把 `human_tasks/` 变成另一棵制品仓库。

## 5. Blind 的特殊处理

Blind 同样要给 curator 提供短路径，但**不能**在方法开发者使用的 LinkRag-Eval 工作区建立指向 Blind 正文的符号链接。正确做法是：

1. 在独立 curator checkout、独立本地目录或权限隔离环境中建立相同的 `human_tasks/<task-id>/` 浅入口；
2. 主工作区只保存 opaque package ID、root hash、允许的资格状态和 receipt；
3. M1 完全冻结前，主工作区的 `human_tasks/` 不出现 Blind 正文、条数、候选统计或可解析链接；
4. Gate B 合法解锁后，仍由一次性 runner 读取冻结 canonical 包，不通过人工入口运行方法。

短路径是人机界面要求，不能覆盖 Blind 隔离要求。

## 6. 生命周期

每个人工任务固定经过以下状态：

1. `CANONICAL_PACKAGE_LOCKED`：机器层包、schema、ID、行数和 manifest 已冻结；
2. `HUMAN_ENTRYPOINT_VALIDATED`：浅入口、角色隔离、指南和链接通过校验；
3. `AWAITING_HUMAN_SUBMISSION`：可以正式交付；
4. `SUBMISSION_RECEIVED_UNREAD`：研究员声明完成，但答案尚未解析；
5. `SUBMISSION_LOCKED`：按原始字节完成提交锁；
6. `MECHANICALLY_VALIDATED`：锁后检查 schema、ID、枚举和完整性；
7. `ADJUDICATED_OR_FINALIZED`：按冻结规则仲裁或形成最终记录；
8. `ENTRYPOINT_CLOSED`：入口不再接收修改，后续只读取 canonical 制品。

不得从第 1 步直接跳到第 3 步；“canonical 包存在”不等于“适合交给研究员”。

## 7. 校验与拒绝条件

交付前运行：

```bash
PYTHONPATH=src .venv/bin/python scripts/check_robust_fusion_human_task_entrypoints.py --before-handoff
```

校验至少覆盖：

- 人工入口和指南均使用项目根目录相对路径；
- 可见文件路径不超过四个组成部分；
- 工作区是符号链接而不是复制目录；
- 链接精确指向注册的 canonical 包且没有越出项目根目录；
- 必需输入、行数和允许文件集合一致；
- 指南不出现 `runs/`、`data/robust_fusion/`、`docs/plans/` 或绝对本机路径；
- 预交付时 `submission.csv` 尚不存在；
- 每个未来人类接触点都声明“交付前必须建立浅入口”；
- Blind 人工任务声明 curator-only 工作区，不能注册到活动方法工作区。

任一失败都停止交付；它不影响 canonical 包本身的历史有效性，但该包不能直接交给研究员。

## 8. 明确禁止的做法

- 在聊天里给研究员一条六七层 `runs/...` 路径，让其自行寻找；
- 只说“进入 relation 文件夹”，却不提供从项目根目录出发的唯一入口；
- 把同一任务复制到桌面、下载目录和项目目录三处，再人工选择哪份是最终提交；
- 把 A/B、仲裁员和 facilitator 的文件放在同一可浏览目录；
- 让 Blind curator 为了路径简短而在主方法工作区建立明文链接；
- 在人工填写期间切换 `CURRENT` 或其他可变别名，使同一路径突然指向另一任务；
- 把浅入口当成新真值层，绕过原 canonical manifest、提交锁或 finalizer。

