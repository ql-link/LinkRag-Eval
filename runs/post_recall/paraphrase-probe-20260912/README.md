# Issue #22：英文保义改写探针

2026-09-13 修复交接：对应输入、36 项 AI 逐条意见及用户整体接受记录现纳入 Git，审核页从这些记录恢复进度。此前 PR #43 只提交工具和摘要，漏掉了已有接受记录，导致合并后仍显示全部未审核。准备阶段：已取得原始输入，生成 24 个 AI 改写草稿，完成 36 项独立 AI 预审，并准备审核页面、运行入口与离线汇总。**真实人工审核 0/36，正式模型评分 0 条；本 Issue 尚未完成。** 用户已接受 AI 预审结论并保留现有措辞；该整体接受与逐项人工审核分别记录，不把工程 fake 分数或模拟审核写入真实结果。

任务依据：[Issue #22](https://github.com/ql-link/LinkRag-Eval/issues/22)、[研究计划 §1.3](../../../docs/plans/post-recall-research-plan.md#13-current-direction)。初始准备基于 `863f5a0`，PR #43 已合并；本次持久化修复基于 `master` 的 `0569616`，分支 `fix/issue-22-review-handoff`。本次不增加模型推理结果，不关闭 #22。后续冻结记录当时实际 HEAD 和会影响执行的源码内容摘要，用于防止审核／配置固定之后换输入或换代码。

## 给审核者

打开 [review.html](review.html)，按 [审核说明](REVIEW_GUIDE.md) 检查英文。页面按 12 个场景排列，每个场景依次显示原版、同义改述版、实体换名版，共 36 项。填写实际审核人、日期和辅助方式，逐项作出通过／需修改／未决判断。可以中途导出并稍后导入；**不要用本轮模型输出帮助决定预期答案**。

导出 `issue22-human-review.jsonl` 后交回执行者。页面是独立离线 HTML，无外部字体、脚本或网络请求。中文是 AI 辅助释义，英文才是待审核输入；界面不显示模型评分。`human-review-template.jsonl` 只是空白模板；`human-review.jsonl` 才保存实际回收的人工记录，目前为空。

[独立 AI 预审](ai-review/report.md)对 36 项均建议“未发现明确问题”，逐条意见与输入摘要见 [ai-review/review.jsonl](ai-review/review.jsonl)，用户整体接受记录见 [review-state.json](review-state.json)。该结果不等于真人通过。当时提请确认的三个口径为：`paints murals` 改为 `creates murals by painting` 是否偏窄、`but` 改为 `and` 是否允许弱化对比语气、`can/cannot` 是否采用能力读法。本地原始记录保存了用户“你的审核没有问题，可以了”的整体接受，现补入 Git，草稿保持原样。接受范围覆盖上述措辞，不再将它们列为未答复；非优选段落缺少证据也不等于其中未提及的活动为假。

## 输入来源与范围

- 用户提供 `/Users/fang/Downloads/stage-a/`。只读取、逐字节复制 `control-scenes.json` 与 `control-texts.jsonl` 到本目录 `source/`；没有查看该目录其他评分或旧结果，也没有更改原文件／共享源目录。
- 12 个 `probe_id` 唯一，24 段不同正文；配套正文清单是 24 段正文＋16 个不同查询，共 40 行，与源场景精确对应。源文件已有 `paraphrases` 是 16 个不同查询清单的一部分，不直接当作本轮完整改写或人工审核证据。
- 内容为 4 组“活动＋能力”关系，分别有跨句重复人名、同句多个主体、共享主语三种句式。**12 个场景并非 12 个独立话题**，不做独立样本置信区间或外推总体错误率。
- `scenes-original.jsonl` 的初版正文、查询和预期偏好保持源文件原样。`scenes-paraphrased.jsonl` 包含 12 个同义改述、12 个实体换名版本；全部使用英文。每个版本记录源 ID、版本 ID、改写类型、两段正文、两个查询、两个预期偏好、生成者和修订关系。当前会话未暴露准确的生成模型 ID，诚实记为 null，未猜测。
- 同义版改述活动、能力表达和正向查询的条件顺序，属于待人工确认的保义草稿。换名版只一致替换人名；原查询没有人名，因此查询保持不变，避免同时引入其他改动。

最初来源核对保留在本地 `source-audit.json`，原件本身现纳入 Git。计数和英文对应关系的机械检查不能替代语义审核。

## 本地准备与回收

下列命令从仓库根目录执行。依赖环境只放在本任务目录，可删除后按命令重建；不要求显卡、生产 RAG 包、数据库或检索服务。

Git 现在跟踪 `source/` 两个原件、两份 `scenes-*.jsonl`、`ai-review/review.jsonl`、`review-state.json`、`human-review.jsonl` 和生成的 `review.html`。新克隆可以直接打开审核页，也可用 `prepare` 重建，无需另取本机数据。原始会话收据 `review-acceptance.json` 继续本地保留；可移交版本 `review-state.json` 省略会话 ID，保留原话、范围和与输入的对应校验。分发 ZIP、运行环境和资源日志继续忽略。

```bash
RUN=runs/post_recall/paraphrase-probe-20260912
uv venv --python 3.12 "$RUN/.venv"
uv pip install --python "$RUN/.venv/bin/python" -e '.[dev,ltr]'
"$RUN/.venv/bin/python" "$RUN/probe.py" prepare

# 收到实际审核文件后；脚本保留原提交，并将新的真人记录追加到 human-review.jsonl。
"$RUN/.venv/bin/python" "$RUN/probe.py" receive /绝对路径/issue22-human-review.jsonl
```

`draft.py` 仅用于在没有输出的目录中重建初稿，拒绝覆盖初稿文件；当前草稿已经生成，无须再次运行。`prepare` 从已保存的 AI 意见、整体接受与逐项人审记录重建页面，同时生成空白填写模板；空白模板不是审核结果。新的人审收件写入 `human-review.jsonl` 后，重新生成页面并提交这两个文件即可跨机器恢复。浏览器自动保存是填写草稿，尚未导出、回收并提交的编辑不会自动进入 Git。审核记录绑定本版本的英文输入／预期偏好，以及页面所示参照原版的版本 ID 与内容摘要，防止旧审核错误地套到改过的材料或原版上。原版自身的审核参照本版本；缺少参照原版字段的旧空白模板需重新生成。

如需修改，保留旧行，在对应 `scenes-*.jsonl` 末尾增加下一版，更新唯一 `version_id`、`revision` 与 `supersedes`；`supersedes` 指向同场景、同改写类型的上一版。修改中文辅助释义和理由以与新英文对应。重新运行 `prepare`；新版本必须实际重新审核，旧记录不会自动迁移。原版如确需修订，也保留原始 v1 和源文件，新版修订原因写在 `drafting_notes`；同场景的两份改写即使文本未变，也须相对新版原文重新确认等价。页面导入与 `receive` 拒绝参照旧原版的提交；历史原提交及审核行保留，但不再授权冻结。不得仅替换旧审核的参照字段代替真人重审。不删除有歧义场景来维持数量。

## 审核齐全后固定执行配置

核实服务器实际加载的 Qwen 权重 revision、运行环境与 GPU，把事实填入 `runtime-record.json`。以下字段是格式说明；`operator_confirmed=false`，不能原样用于推理：

```json
{
  "qwen_revision": "31c69efc29464b6bb0aee1398b5a7b50a99340c3",
  "qwen_server_environment": "",
  "qwen_deployment_evidence": "",
  "gpu": "",
  "gpt_access": "",
  "operator_confirmed": false
}
```

`qwen_deployment_evidence` 记录实际加载的固定 revision 的核查依据，不能仅凭服务模型名称推断；`gpt_access` 记录实际 Codex 入口／身份可用情况，不写密钥。`probe.py freeze` 只有全部 36 个有效版本经真人通过后才会创建 `frozen/` 和 `execution-config.json`。当前没有这两个正式执行产物。

```bash
"$RUN/.venv/bin/python" "$RUN/probe.py" freeze --runtime-record "$RUN/runtime-record.json"
```

固定的判断器为 Qwen3-14B-AWQ thinking、temperature=0、输出上限 6144、上下文 8192；GPT 参照为 `gpt-6-astra`、low。两者均沿用 `judge_prompt_v1` 和 0–4 分 schema。Qwen 使用 4 workers，GPT 使用 2 workers，batch size **均为 1**；每次判断只见一个查询和一段正文，提示中不含预期偏好、人审记录或其他候选。生成随机种子未设置，`20260910` 只打乱派发顺序；GPT 权重 revision 与训练数据未知。

## 正式推理与首轮保存

Qwen 可以使用负责人提供的 `ssh runpod` 服务器。下面通过 SSH 把服务器 8000 端口转到本机 18000；服务须已按前述 revision 和参数启动，不在本任务中重选模型。

```bash
# 独立终端维持隧道：
ssh -N -L 18000:127.0.0.1:8000 runpod

# 先完成 freeze，再从仓库根目录运行两个模型：
"$RUN/.venv/bin/python" "$RUN/run_model.py" --model qwen --endpoint http://127.0.0.1:18000
"$RUN/.venv/bin/python" "$RUN/run_model.py" --model gpt

# 两个模型均有保存结果后，纯离线生成 results.json 与 report.md：
"$RUN/.venv/bin/python" "$RUN/probe.py" evaluate
```

若服务需要认证，只通过 `--api-key-env 环境变量名` 传递；日志不保存认证 header。运行入口实际调用现有 `scripts/llm_judge_pilot.py judge`，记录包装只额外保存 HTTP 响应正文、usage 和起止时间，不改提示／schema／排序实现。输入构造与评价逐场景调用旧英文探针函数：每次只含该场景两段、两个查询，绝不把独立英文场景拼成共享候选池，也不伪装成中文。

最小规模为每模型 36×2×2＝**144 条逻辑评分**。已有 CLI 会对完全相同的查询＋正文在本轮去重，并会自动重试失败；实际请求与逻辑评分数分开记录。执行前拒绝可命中的历史缓存。每个模型只建立一个新运行目录，重复运行拒绝覆盖。

`inference/<模型>/raw/` 保存现有 CLI 的全部批次、重试、最终恢复分数、原始响应和映射；**主结果另存 `first-pass-scores.jsonl`，只取每个初始批次首次尝试，首次失败仍算不可用，绝不以重试成功覆盖**。同一初始批次内部可能出现现有运行器的 HTTP 400 schema fallback，该物理请求同样留存并计数；它不被隐藏。中断的在途项与尚未派发项分别保留，不能自动续跑或把空缺补成正确。若后续确需补充运行，另存并明确其身份，不覆盖首轮。

Qwen 成功 HTTP 响应原文和已观测 token 数可核验；错误响应正文不保存，避免回显凭据。GPT 原始 stdout／stderr、命令及输出 JSON 保存，Codex 内部供应商请求数、无法确认的 token 或账单金额保持未知，不从进程数推算。当前没有实际推理成本，也没有连接或启动 GPU。

## 统计与解释

每模型按原版／同义／换名报告严格正确、逆序、同分、不可用；正确率分母包括全部 24 个查询方向。同分和不可用不算正确。

一致率对每个原版及对应改写的同一查询方向进行比较，分母是双方可用的方向。单独报告排除的不可用数、双方同分数、单边同分数，并再报告排除任何同分后的严格方向一致率。同时列出双方都正确与双方都逆序：两次都错但方向相同只算一致，不算正确。程序按固定输入顺序列出改变判断／仍逆序的前 8 个例子，完整结果均保留。

本探针只回答小样本措辞／实体敏感性，不证明模型从未见过 NevIR，不排除训练污染，不替代 #20，不用于选模型／改提示。没有完整训练数据清单就保留未知；当前报告不引入未经查证的公开日期或训练截止日期。若后续添加这些事实，须核验原始发布／模型资料并给出直接来源。

## 验证与版本管理

```bash
"$RUN/.venv/bin/python" -m pytest "$RUN/test_probe.py" -q
"$RUN/.venv/bin/ruff" check --no-respect-gitignore "$RUN"/*.py
python3 scripts/build_report_index.py --check
```

本次持久化修复通过仅 Git 文件重建、全新浏览器恢复、24 项专项测试及完整回归，详见[交接修复验证](checks/review-handoff-20260913/verification.json)。PR #43 的历史检查保留在 [原验证记录](checks/pr-validation-20260913.json)。`test_probe.py` 自建独立的合成夹具，新克隆无需私人研究数据即可运行；这些夹具不能用于正式实验。浏览器验证需先生成本地审核页面，再安装 `playwright` 和 Chromium，执行 `qa_browser.py`。模拟提交仅存在于临时目录和隔离浏览器，不当作真实人审或实验结果。

本次在 `.gitignore` 为上述实际审核材料添加精确白名单，保留原始英文和审核记录原样。生成页面展示“AI 预审”“用户整体接受”“逐项人工审核”三种状态；接受记录与输入／意见不匹配时显示已过期，不沿用为当前结论。空的人审文件仍为空；整体接受不会伪造 36 条独立人审。环境、凭据、原始会话收据和运行日志继续忽略。共享入口在最后一个提交追加准备状态。没有新增正式实验报告，因此 `REPORT_INDEX.md` 只运行生成器 `--check`，不手改自动生成索引或把准备工作登记成效果实验。

当前已有的整体接受已保存并可随 Git 恢复。原 issue 的逐项人审要求尚无对应提交；后续按实际审核口径如实补齐，不能把整体接受自动冒充独立逐项复核。执行顺序仍为：满足当前执行要求的审核记录 → 必要修订 → 核实资源并 freeze → 两模型正式推理 → 结果／成本复核 → 实验台账及共享入口登记 → 结果 PR。当前准备阶段的 PR 可先行审核，不代表 Issue 可以关闭。
