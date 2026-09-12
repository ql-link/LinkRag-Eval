# #20 官方 Test 主方案：实例已关机，结果回收受阻

配置与执行代码已纳入本地提交 **`b4d01d7bae361f72ab83643cc0a9df7280e06e65`**，未推送，并通过 Git archive 将该版本部署到替代 GPU。2026-09-11 17:33:29 UTC 开始 E0，17:34:43 完成全部 2,766 查询，73.442 秒；Qwen 单次 worker 于 17:33:42 UTC 启动，PID 55064，顺序执行 L1 与 L2。L1 已于 18:22:19 UTC 完成并回收核验；2026-09-12 00:59–01:01 UTC 检查发现实例已关机且余额不足，L2 最终完成状态与退出记录尚待回收确认。BGE 权重及分词器已在本机下载并校验，暂未上传或推理。原 #23 成员 Test 聚合继续保存在 [nevir-test-final-20260911](../nevir-test-final-20260911/README.md)，不在本目录覆盖或复用为判断缓存。

## 输入与固定方案

输入来自 [#19 已验收快照](../nevir-test-candidates-20260910/README.md)，包含 2,766 查询、1,383 对。主评价采用官方标签可用、两段共同覆盖且无结构冲突的 **2,736 查询／1,363 完整配对／699 来源组**；另报含结构冲突的 2,738 查询敏感性结果。跨划分 4 个完全相同段落保留。成员已有 E0／融合／N=8 Test 聚合已曝光，不能把这次准备称为从未曝光的完整 Test；此前没有 Qwen Test 输出。

主方案沿用既有 Qwen3-14B-AWQ（revision `31c69efc29464b6bb0aee1398b5a7b50a99340c3`）、thinking、`judge_prompt_v1`、温度 0、上下文 8,192、输出上限 6,144、8 workers。只评价固定融合前 **K=20**，判断分相同用融合分破同分；E0 破同分结果单列辅助对照，不根据 Test 选择 K、触发策略、模型或提示。固定模型及运行参数见 [frozen-config.json](frozen-config.json)。

| 输入 | 逻辑条数 | 查询数 | 计划唯一模型请求／输入 |
| --- | ---: | ---: | ---: |
| L1 指定两段 | 5,476 | 2,738 | Qwen 5,472 |
| L2 固定融合 Top20 | 55,320 | 2,766 | Qwen 55,260 |
| BGE 两层输入并集 | 55,502 | 2,766 | BGE 55,502 |

Qwen 每个任务使用全新独立缓存，每个唯一输入只请求一次，不重试、不作 schema fallback；两任务合计 **60,732 次计划请求**，实际完成数读取远端 progress.json。L1 不可用项保留在准确率分母，配对区间只用共同可用项；L2 任一判断不可用则整个查询回退到原固定融合。全查询都生成 Top20 输入，评价时才按事先口径筛选，不能只推理较容易的覆盖子集。

BGE 沿用 `BAAI/bge-reranker-v2-m3` 固定 revision `953dc6f6f85a1b2dbfca4c34a2796e7dde08d41e`，保留连续原始 logits，不转成 0–4 分。其 [配置](bge/execution-config.json) 与 [运行脚本](bge/run_bge.py) 沿用已执行的开发／确认参照，适配 Test 角色及配置中的新模型路径；本次模型推理和完整分词检查仍待执行；计算过程不变。E0 使用当前英文基线，配置中的摘要用于启动时核对模型包身份，不重训。

## 已执行的离线工作

```bash
.venv/bin/python runs/post_recall/nevir-test-main-20260911/prepare.py
```

已执行一次，完成于 2026-09-11 13:11:24 UTC，75.451 秒；记录在 [preparation.json](preparation.json)。只重建原固定融合分用于选池，未算准确率。该生成命令拒绝覆盖现有输入／配置，后续使用已生成文件，不再次生成另一套 Test 配置。配置补齐英文基线身份，并明确 BGE 的两层并集共享分数，最终保存时间见 JSON 的 configuration_completed_at，早于本次正式 Test 评分；生成时 HEAD 为 `23f465d`，Test 角色支持和本目录脚本在离线准备时属于未提交差异；正式执行所用版本由独立启动记录和 E0 运行摘要记录，配置内 code_commit 明确表示准备基准版本。

[offline-validation.json](offline-validation.json) 记录实际输入核验：L1 指定段、L2 全查询精确 Top20、唯一请求计数、BGE 并集的标识／文本／层级均一致；30 份交付原件仍保留，根目录临时包已清理。完整非 integration 回归 1,310 passed、23 skipped、3 deselected，6 项既存 warnings；离线阶段相关合成测试 48 项通过；替代实例的单次远端 worker 增补测试后，相关测试共 50 项通过，Ruff 通过。检查只输出聚合数；不展示 Test 单题内容或分数。

## 替代实例与 35GB 存储安排

连接为 `ssh -p 12981 root@connect.nmb1.seetacloud.com`，密码仅用于此次 SSH 认证，不写入仓库或运行记录。首次检查 GPU 为 RTX 4090 24GB、driver 580.76.05；系统盘可用约 30GiB、数据盘约 38GiB。原有其他任务的数据目录约 13GiB，保留不动。

- 独立运行环境：`/root/linkrag-eval-test-20260911/gpu-venv-py313/`，使用 Python 3.13.5；vLLM 0.29.0、Torch 2.13.0、Transformers 5.17.0、HF Hub 1.30.0 保持原主要版本。Python／驱动和其余依赖如实记录，不能声称整个二进制环境相同。项目评分驱动另用独立 Python 3.13.5 环境 `judge-venv/`，满足项目 Python >=3.11；它只安装项目基础依赖。首次尝试使用系统 Python 3.10.8；服务在 Triton 读取带 lambda 装饰器的 MiniMax 内核源码时失败，未处理任何模型请求。同一最小源码读取复现，在 3.10 缺少函数正文、在 3.13 返回完整函数，因此改用 3.13，保持 GPU 包版本，并保留首次失败日志；不修改 vLLM／Triton 源码。新环境验证后已删除本任务中失效的旧 GPU 环境，199 项依赖的版本集合完全一致。
- 模型与服务缓存：`/root/autodl-tmp/linkrag-eval-test-20260911/`。Qwen 必需文件共 9,992,654,711 字节，固定 revision 的权重按官方 SHA256 校验；BGE 约 2.3GB，待 Qwen 完成、结果保存在本机后再传入。
- 安装下载与解包缓存使用本任务专属 `/dev/shm/linkrag-eval-test-20260911/`，位于 60GiB 共享内存盘；不在磁盘保留第二套 wheel 缓存。安装完成后已清理该临时安装缓存（新环境这次释放约 7.5GiB）。
- 原计划把驱动留在本机；确认 GPU 环境实际只占约 7.95GB 后，将约 58MB 固定评分输入和小型项目驱动也迁入服务器，避免本机休眠／断网打断一次性长实验。驱动以独立进程运行，请求远端 127.0.0.1:8000，预留 4GB 给逐请求文件及缓存，结束后回收结果。服务器不复制 SQLite、全候选或历史 runs；BGE 只传对应的 55,502 项输入及小脚本。
- `serve.py` 启动前检查两个独立磁盘目录的文件总量不超过 35,000,000,000 字节。推理期间检查实际容量；只清理本任务可重新下载的模型／编译缓存，结果及其他任务文件不作为空间回收对象。

新实例直连 Hugging Face 失败；Qwen 必需文件先从官方固定 revision 下载到本机 `model-staging/`，9 文件校验通过，耗时 813.404 秒。SSH 大文件传输偏慢，随后核对 Qwen 在 ModelScope 发布的两份权重，其大小和 SHA256 与已验证的 Hugging Face 固定 revision 完全一致，改由实例直接下载相同权重；该传输于 2026-09-11 16:01:45 UTC 完成，342.140 秒，两份权重均校验通过。配置／分词器等小文件仍来自 Hugging Face 原件。安装使用可访问的 PyPI 镜像。这些属于部署过程，不是 Test 推理重跑；原离线准备与校验记录保留其当时状态。实际模型服务、合成 smoke 与运行检查见 [runtime-check.json](runtime-check.json)，完整依赖分别见 [GPU 包版本](runtime-packages.txt) 与 [评分驱动包版本](driver-packages.txt)。

截至 2026-09-11 16:20:49 UTC，任务专属运行目录占 8,522,133,504 字节、模型／缓存目录占 10,107,916,288 字节，合计 **18,630,049,792 字节**，距 35GB 限额约 16.37GB。3 条合成请求于 16:20:16–16:20:18 UTC 完成，2.687 秒，3 次 HTTP 200、3 次正常 stop、0 不可用、0 重试，供应商累计返回 1,041 token；这些只证明接口与格式可用，不构成准确率实验。部署阶段按 5 秒采样的整卡显存峰值 20,969 MiB，包含服务初始化，不能作为正式 Test 的运行峰值。首次服务失败及更换 Python 的证据保留于本机 `provisioning/`；第二次服务于 16:18:01 UTC 启动并完成初始化。完整回归最近一次为 1,312 passed／23 skipped／3 deselected、6 项既存 warnings，相关 50 项测试及 Ruff 均通过。

## 当前执行与后续接续

**负责人已授权本地提交，正式执行使用冻结提交 `b4d01d7`。** #20 要求正式推理前提交冻结配置；该提交固化新实例配置、执行入口与必要测试，研究参数不变。`workflow.py check-ready`、`baseline` 和 `qwen` 会核对主配置及 BGE 配置已按原字节进入 HEAD，否则立即拒绝。提交、部署与启动的时间线已落盘；不修改配置来追认已运行结果。

以下命令已经执行，保留作复现入口；实例现已关机，恢复后先检查已落盘产物，不再次调用 baseline 或 qwen。工作目录为项目根目录。新实例的固定模型 revision、RTX 4090、vLLM／Torch／Transformers 版本与 8,192 上下文已检查；[服务入口](serve.py) 与评分驱动都运行在远端，只连接远端 127.0.0.1:8000。[synthetic_smoke.py](synthetic_smoke.py) 的 3 条独立合成检查已通过，不重复执行，不进入正式缓存。恢复时先确认两份配置及相关实现已提交、部署字节一致及现有服务仍正常；若运行环境或长度检查不符，先解决具体问题。

```bash
.venv/bin/python runs/post_recall/nevir-test-main-20260911/workflow.py check-ready
.venv/bin/python runs/post_recall/nevir-test-main-20260911/workflow.py baseline
.venv/bin/python runs/post_recall/nevir-test-main-20260911/workflow.py qwen
```

截至 2026-09-11 17:40:56 UTC，L1 已完成 850/5,472 个唯一请求，其中 2 个 HTTP 200 回执以 length 结束、未形成合法评分，按原规则保留不可用且不重试；这不是最终失败总数。进程仍运行，任务磁盘约 18.66GB。仅核对失败类型和供应商回执，不查看单题内容或按中间效果调整方案。E0 原始结果在 `baseline/`，Qwen 的 `launch.json`、`worker-start.json` 和 `execution-start.json` 已取回本机。

**L1 阶段完成。** 2026-09-11 18:22:19 UTC 完成 5,472 次唯一请求、5,476 条逻辑评分，2,917.793 秒；23 条不可用均为 HTTP 200／length 回执，每个唯一输入恰好请求一次。完整 `l1-judge/` 已于 18:38:28 UTC 取回本机，评分数量、输入标识、5,472 份请求记录和缓存文件核验通过；原始目录及 `provisioning/l1-receipt.json` 保留，尚未计算准确率。远端单次 worker 随后自动进入 L2，截至 18:36:01 UTC 完成 1,800/55,260 次请求，4 项不可用；服务健康、GPU 100%，任务磁盘约 18.85GB。L1 已经回收，后续完成时只需补收 L2、退出记录和整体资源日志，再按固定方案接续 BGE。

此前已启用当前任务的 15 分钟自动接续（`20-test`，2026-09-12 因下述阻塞暂停）：检查进程、进度与容量；Qwen 完成后先回收完整结果，再启动固定 BGE，最终执行两臂统计和收尾。普通单项不可用按既有规则保留，只有进程异常退出、数据缺损或资源不足等实质故障才需要处理；不自动重跑正式实验。

负责人已授权全部 GPU 推理完成后的自动关机。Qwen 两层和固定 BGE 完成、完整结果及必要资源日志已回收到本机并核验后，通过 computer-use 在 Safari 已打开的 AutoDL 页面关闭实例，再在本机继续统计与文档收尾。2026-09-11 20:42 UTC 已核对目标为 `fb0c4680e1-a580f590`（内蒙 B 区 / 220 机，RTX 4090 单卡），与现有 SSH 返回的 `autodl-container-fb0c4680e1-a580f590` 一致。执行时重新核对实例 ID，选择“关机”并确认页面已关机；不释放或删除实例。此要求已写入原自动接续，GPU 工作尚未结束时保持运行；若页面操作受阻，报告具体原因，不能将待关机记为已完成。

**2026-09-12 结果回收受阻。** 00:59–01:01 UTC 的 SSH 检查均被关闭；Safari 刷新后确认本实例已关机，无卡模式开机入口也提示余额不足，没有成功开机或充值。这次关机不是本任务执行的收尾操作；精确停机原因、时刻和 L2 最终状态尚无远端日志可核对。最后正常快照为 00:43:23 UTC：L2 完成 **54,150/55,260** 次请求、68 项不可用，阶段耗时 22,864.177 秒，服务健康、GPU 100%，任务磁盘 20.367GB；这些是中间累计值，不能当作最终结果。E0 与完整 L1 仍在本机，L2、退出记录及最终资源日志尚未回收，BGE 未启动，#20 保持开放。自动接续已暂停；需要负责人处理 AutoDL 余额后恢复访问，第一步取回现有产物，确认完整性与实际结束状态，再按单次运行规则决定后续，不自动重跑或补跑。观察记录在 `provisioning/interruption-20260912.json`。

`baseline` 在本机执行。启动 Qwen 前，将此次提交中的 `src/`、原严格驱动及本目录执行文件部署到配置中的远端 repository_root，并核对部署配置与本地已提交字节一致。`qwen` 返回远端 PID，不表示完成；远端 `launch.json` 和 `worker-start.json` 都只允许创建一次，重复调用拒绝启动，`process-exit.json` 记录成功／失败退出，不自动重启。定期读两层的 progress.json、GPU 进程与空间；完成后回收两层完整目录及运行记录到本机，再执行：

```bash
.venv/bin/python runs/post_recall/nevir-test-main-20260911/workflow.py evaluate --arm qwen
```

`qwen` 的远端 worker 调用既有严格单次请求驱动 `open-judge-selection-20260911/run_frozen.py`。运行目录包含逐请求耗时、失败类型、供应商 token／结束原因回执及总耗时；输出目录已存在时拒绝重新评分，不自动恢复正式任务。实际中断或需要重跑时依 #20 原要求另行登记，保留已有分数和执行偏差。

Qwen 完成后，把本目录 `bge/` 中的 `items.jsonl`、`execution-config.json`、`run_bge.py` 放到服务器同一新目录，使用 `/root/linkrag-eval-test-20260911/gpu-venv-py313/bin/python <该目录>/run_bge.py` 执行。BGE 的 6 个必需文件已从官方固定 revision 下载至本机 `model-staging/bge-reranker-v2-m3/`，共 2,293,242,108 字节，187.858 秒，文件大小与官方摘要全部通过，记录在其 download.json。GPU 权重尚未部署，须先将固定模型放至配置路径。为缩短后续传输，已验证 BAAI ModelScope 的 model.safetensors 与该固定 revision 权重大小、SHA256 完全一致；可在 Qwen 结果收妥后由服务器直接下载相同权重，重新核验后使用，五个配置／分词器小文件仍复制 Hugging Face 原件。下载 URL 与核验依据见本机 `provisioning/bge-weight-transfer.json`。脚本检查环境与未截断长度；超出 8,192 token 则停止，不静默截断。取回 `scores.jsonl`、`summary.json` 后运行：

```bash
.venv/bin/python runs/post_recall/nevir-test-main-20260911/workflow.py evaluate --arm bge
```

评价复用现有 `evaluate_pairs`／`evaluate_rankers`／`pair_statistics.comparison_table`，同时输出主口径与含冲突敏感性、严格成对准确率、双向正确、列表位置、纠正／改坏、来源组自助 95% 区间（seed 20260910，2,000 次）及逐方向符号检验。预定主比较为 Qwen `stage1_judge − stage1`。逐方向检验未校正组内依赖和多重比较；没有全池相关性标签，不报告全池 nDCG 或答案质量。

所有大输入、逐题输出和运行日志留在本地并受 Git 忽略。实际推理后再将聚合结果纳入轻量产物白名单、更新既有报告与实验台账；L2 最终状态待回收、BGE 未执行，没有最终结果或论文可用的新效果结论。
