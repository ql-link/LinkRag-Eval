# Issue #22：英文保义改写探针

2026-09-13 交付完成：**36/36 项人工审核已接收，两模型各 144 条首轮评分、完整结果与独立复核均已完成。** Qwen 原版／同义／换名严格正确 23／20／23（各 24 方向），GPT 均为 24/24；无重试或不可用。Yifan Yuan 的审核日期为 2026-09-13、方式为人工审核。原版与换名版保持不变，同义版使用已审 v2。

任务依据：[Issue #22](https://github.com/ql-link/LinkRag-Eval/issues/22)、[研究计划 §1.3](../../../docs/plans/post-recall-research-plan.md#13-current-direction)。初始准备基于 `863f5a0`；准备阶段 PR #43 已合并为 `0569616`，当前从该 `origin/master` 建立 `codex/issue22-completion-20260913` 接续，不改写原工作区的未提交内容。实验固定记录包含当时实际 HEAD 和会影响执行的源码内容摘要，用于防止审核／配置固定之后换输入或换代码。

## 本轮执行与产物

执行配置已于 2026-09-13 07:25:33 UTC 固定，代码为 `d4b7880`。两模型首轮各 144 条评分均独立复核通过，`probe.py evaluate` 已一次生成两模型最终汇总。Qwen 评分 100.404 秒、GPT 1,499.811 秒；Qwen 144 次 HTTP 全成功，GPT 144 个 Codex 进程正常退出，供应商内部请求和 token 用量未知。GPU 日志已回收，Safari 确认实例于北京时间 15:31 关机。已完成结果与边界见[本轮报告](../../../docs/reports/paraphrase_probe_2026_09_13.md)，最终状态以本节和项目当前状态为准；下方收件段落描述推理之前的验收。

2026-09-14（#48）：探针从完成后的 `summary.json` 或中断时已写入的 `mapping.jsonl` 读取实际生成参数，按同一缓存键重建首轮评分；旧产物仍按旧键读取。执行前的历史缓存检查按缓存自身记录的参数识别相同文本，保留原 model／effort／prompt_version 边界，不依赖输入 ID 或旁侧映射文件；该检查只阻止重复首轮，不会把缓存并入新运行。原实验结果、执行配置与代码版本 `d4b7880` 不变。当前代码已与当时冻结的 `code_files` 不同，后续新实验须另存输入与输出并重新 freeze，不覆盖本轮产物。

- 随版本保留：[执行配置](execution-config.json)、[轻量聚合](summary.json)、本文及正式报告。
- 本地完整结果：[results.json](results.json)、[程序报告](report.md)；首次评分和原始过程见 `inference/qwen/`、`inference/gpt/`，两者各有 `execution-summary.json`。
- 本地审核与输入：`review-submissions/`、`human-review.jsonl`、两份 `scenes-*.jsonl` 和 `frozen/`。
- 本地核验与资源：`provisioning/independent-{qwen,gpt}-validation.json`、测试日志、部署及显存记录、`shutdown-receipt.json`。本轮所有评分已保存在本机，实例关机不影响离线分析。

## 本次收件与验收

- 原提交 `/Users/kawauso/Downloads/stage-a/paraphrase-probe-reviewed.json` 逐字节保留在 [收件目录](review-submissions/received-20260913/)，不修改下载原件。该文件是包含 36 个场景的 JSON，不是浏览器导出的审核 JSONL；审核者、日期与辅助方式来自负责人本次明确回复，保存在 `reviewer-metadata.json`。
- 对照既有源文件及草稿，12 个原版、12 个换名版的所有提交字段完全一致；12 个同义 v2 的版本号和修改范围符合提交说明。全部预期偏好仍为 `[0, 1]`，72 个查询方向没有缺项或重复。Codex 对全部内容的补充语义复核未发现错标，不计作第二名人工审核者。
- 12 个同义版的否定查询恢复 `but`；三个壁画同义版保留 `paints murals`，不再引入 `creates`。提交说明明确接受无许可语境时 `can/cannot` 与 `able/unable` 的能力读法，并保留“未提及不等于否定”的解释。原 AI 预审报告描述的是 v1，不能据此声称 v2 已接受过同一次预审。
- 保留全部 v1 历史，追加 12 个 v2 及 `revision=2`、`supersedes`；审核关联当前英文与参照原版。`normalized-human-review.jsonl` 如实说明由已审场景和负责人补充信息转换，不宣称这些字段来自浏览器逐项点击。现有 `receive` 接收 36 条 `approved`，`approved_reviews` 对全部 36 个有效版本通过。转换没有改变提交的英文或预期偏好。
- [验收记录](review-submissions/received-20260913/acceptance.json)与 `receipt.json` 保存计数和收件结果。现有 20 项合成测试通过；正式输入构造为每模型 144 条逻辑评分。收件当时无模型请求、GPU 操作或效果实验；后续正式执行产物见上方。

## 给审核者

打开 [review.html](review.html)，按 [审核说明](REVIEW_GUIDE.md) 检查英文。页面按 12 个场景排列，每个场景依次显示原版、同义改述版、实体换名版，共 36 项。填写实际审核人、日期和辅助方式，逐项作出通过／需修改／未决判断。可以中途导出并稍后导入；**不要用本轮模型输出帮助决定预期答案**。

导出 `issue22-human-review.jsonl` 后交回执行者。页面是独立离线 HTML，无外部字体、脚本或网络请求。中文是 AI 辅助释义，英文才是待审核输入；界面不显示模型评分。`human-review-template.jsonl` 只是空白模板；`human-review.jsonl` 保存实际回收的人工记录，现有 36 条通过记录。已完成本批审核，无须重新填写空白模板。

[独立 AI 预审](ai-review/report.md)保留准备阶段对 36 个 v1 的判断；原工作区另存逐条意见 `ai-review/review.jsonl`。当时提出的壁画措辞、对比连词及能力读法三个问题已由本次提交处理，具体修改见上方收件记录。非优选段落缺少证据仍不等于其中未提及的活动为假。

## 输入来源与范围

- 用户提供 `/Users/fang/Downloads/stage-a/`。只读取、逐字节复制 `control-scenes.json` 与 `control-texts.jsonl` 到本目录 `source/`；没有查看该目录其他评分或旧结果，也没有更改原文件／共享源目录。
- 12 个 `probe_id` 唯一，24 段不同正文；配套正文清单是 24 段正文＋16 个不同查询，共 40 行，与源场景精确对应。源文件已有 `paraphrases` 是 16 个不同查询清单的一部分，不直接当作本轮完整改写或人工审核证据。
- 内容为 4 组“活动＋能力”关系，分别有跨句重复人名、同句多个主体、共享主语三种句式。**12 个场景并非 12 个独立话题**，不做独立样本置信区间或外推总体错误率。
- `scenes-original.jsonl` 的初版正文、查询和预期偏好保持源文件原样。`scenes-paraphrased.jsonl` 包含 12 个同义改述、12 个实体换名版本；全部使用英文。每个版本记录源 ID、版本 ID、改写类型、两段正文、两个查询、两个预期偏好、生成者和修订关系。当前会话未暴露准确的生成模型 ID，诚实记为 null，未猜测。
- 同义版改述活动、能力表达和正向查询的条件顺序，当前 v2 已经人工审核；壁画场景只改能力表达和查询结构，保留原活动措辞。换名版只一致替换人名；原查询没有人名，因此查询保持不变，避免同时引入其他改动。

来源核对见 [source-audit.json](source-audit.json)。计数和英文对应关系的机械检查不能替代语义审核。

## 本地准备与回收

下列命令从仓库根目录执行。依赖环境只放在本任务目录，可删除后按命令重建；不要求显卡、生产 RAG 包、数据库或检索服务。

源文件、逐条草稿／审核、生成的 `review.html` 和分发 ZIP 继续只保留本地。新克隆取得原有两个源文件后可以用 `draft.py` 重建 v1，但这不会恢复当前 v2 或人审记录；接续正式实验应同时取得本次收件目录、含历史版本的两份 `scenes-*.jsonl` 与 `human-review.jsonl`。不要用测试夹具补造研究输入。本工作区已有这些产物，跳过重建初稿步骤即可。

```bash
RUN=runs/post_recall/paraphrase-probe-20260912
uv venv --python 3.12 "$RUN/.venv"
uv pip install --python "$RUN/.venv/bin/python" -e '.[dev,ltr]'
# 仅新克隆，且已取得 source/ 两个原件时：
"$RUN/.venv/bin/python" "$RUN/draft.py"
"$RUN/.venv/bin/python" "$RUN/probe.py" prepare

# 收到实际审核文件后；脚本保留原提交，并将新的真人记录追加到 human-review.jsonl。
"$RUN/.venv/bin/python" "$RUN/probe.py" receive /绝对路径/issue22-human-review.jsonl
```

`draft.py` 仅用于在没有输出的目录中重建初稿，拒绝覆盖初稿文件；当前草稿已经生成，无须再次运行。`prepare` 重新生成审核页面与空白模板，不清空人审历史。审核记录绑定本版本的英文输入／预期偏好，以及页面所示参照原版的版本 ID 与内容摘要，防止旧审核错误地套到改过的材料或原版上。原版自身的审核参照本版本；缺少参照原版字段的旧空白模板需重新生成。

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

`qwen_deployment_evidence` 记录实际加载的固定 revision 的核查依据，不能仅凭服务模型名称推断；`gpt_access` 记录实际 Codex 入口／身份可用情况，不写密钥。`probe.py freeze` 只有全部 36 个有效版本经真人通过后才会创建 `frozen/` 和 `execution-config.json`。本轮已生成这两个正式执行产物，现有目录无需再次冻结。

```bash
"$RUN/.venv/bin/python" "$RUN/probe.py" freeze --runtime-record "$RUN/runtime-record.json"
```

固定的判断器为 Qwen3-14B-AWQ thinking、temperature=0、输出上限 6144、上下文 8192；GPT 参照为 `gpt-6-astra`、low。两者均沿用 `judge_prompt_v1` 和 0–4 分 schema。Qwen 使用 4 workers，GPT 使用 2 workers，batch size **均为 1**；每次判断只见一个查询和一段正文，提示中不含预期偏好、人审记录或其他候选。生成随机种子未设置，`20260910` 只打乱派发顺序；GPT 权重 revision 与训练数据未知。

## 正式推理与首轮保存

本轮实际使用负责人提供的 AutoDL RTX 4090，沿用固定权重与现有环境。执行时通过 SSH 将服务器 8000 端口转到本机 18022；服务须已按前述 revision 和参数启动，不在本任务中重选模型。以下保留实际连接与推理命令供复现，当前正式运行已完成，不应再次调用。

```bash
# 独立终端维持隧道：
ssh -p 12981 -N -L 18022:127.0.0.1:8000 root@connect.nmb1.seetacloud.com

# 先完成 freeze，再从仓库根目录运行两个模型：
"$RUN/.venv/bin/python" "$RUN/run_model.py" --model qwen --endpoint http://127.0.0.1:18022
"$RUN/.venv/bin/python" "$RUN/run_model.py" --model gpt

# 两个模型均有保存结果后，纯离线生成 results.json 与 report.md：
"$RUN/.venv/bin/python" "$RUN/probe.py" evaluate
```

若服务需要认证，只通过 `--api-key-env 环境变量名` 传递；日志不保存认证 header。运行入口实际调用现有 `scripts/llm_judge_pilot.py judge`，记录包装只额外保存 HTTP 响应正文、usage 和起止时间，不改提示／schema／排序实现。输入构造与评价逐场景调用旧英文探针函数：每次只含该场景两段、两个查询，绝不把独立英文场景拼成共享候选池，也不伪装成中文。

最小规模为每模型 36×2×2＝**144 条逻辑评分**。已有 CLI 会对完全相同的查询＋正文在本轮去重，并会自动重试失败；实际请求与逻辑评分数分开记录。执行前拒绝可命中的历史缓存。每个模型只建立一个新运行目录，重复运行拒绝覆盖。

`inference/<模型>/raw/` 保存现有 CLI 的全部批次、重试、最终恢复分数、原始响应和映射；**主结果另存 `first-pass-scores.jsonl`，只取每个初始批次首次尝试，首次失败仍算不可用，绝不以重试成功覆盖**。同一初始批次内部可能出现现有运行器的 HTTP 400 schema fallback，该物理请求同样留存并计数；它不被隐藏。中断的在途项与尚未派发项分别保留，不能自动续跑或把空缺补成正确。若后续确需补充运行，另存并明确其身份，不覆盖首轮。

Qwen 成功 HTTP 响应原文和已观测 token 数可核验；错误响应正文不保存，避免回显凭据。GPT 原始 stdout／stderr、命令及输出 JSON 保存，Codex 内部供应商请求数、无法确认的 token 或账单金额保持未知，不从进程数推算。本轮实际计数、耗时和已知／未知费用见上方及正式报告。

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

准备阶段检查见 [PR 验证记录](checks/pr-validation-20260913.json)；本轮正式执行前另完成 1,320 passed／23 skipped／3 deselected 的完整非 integration 回归、20 项探针测试与 Ruff，执行后完成两模型逐项及独立统计复核，见 `summary.json` 和 `provisioning/`。`test_probe.py` 自建独立的合成夹具，新克隆无需私人研究数据即可运行；这些夹具不能用于正式实验。浏览器验证需先生成本地审核页面，再安装 `playwright` 和 Chromium，执行 `qa_browser.py`。模拟提交仅存在于临时目录和隔离浏览器，不当作真实人审或实验结果。

准备 PR 已提交脚本、HTML 模板、操作说明、AI 预审报告与轻量验证记录。本轮追加正式报告、执行配置、轻量聚合，并在现有实验台账登记 N16；通过生成器更新报告索引。环境、原件、逐条草稿／审核和完整运行结果继续在本地保留。实验实际代码版本仍是 `d4b7880`，收尾仅增加结果与文档，不改冻结的运行实现。

本 Issue 无剩余标注或 GPU 计算任务。结果供论文稳健性与限制分析引用；#25 的论文整合属于后续写作，不能把本探针解释为已排除训练污染。
