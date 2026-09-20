# 复现包文档清理候选

本目录提交针对正式复现附件的可应用补丁和核验证据。清理两份说明文件中的五处内部流程文字，保留研究来源及验证事实。原包共 39 个文件；仅 `README.md`、`SELF_CHECK.md` 和 `checksums.json` 改变，其余 36 个文件逐字节不变。

## 范围

[changes.patch](changes.patch) 删除 `Origin Skill`、`Origin Mode`、旧任务的 Git/发布操作说明，并将“按 ARS 清单”改为不依赖内部流程名称的统计检查表述。保留验证日期、范围、版本、历史 8 项测试结果、全部实际命令、模型与工具、提示词、参数、数据来源、许可及归属。

`manifest.json` 的历史 `publication` 字段原样保留；它属于本轮受保护的结构化来源记录，不代表当前 Release 的发布状态。其他科学文件、可执行代码、数据、评分、配置和 `expected/` 全部原样保留。没有把自动检查改写成人工审核或第三方认证。

## 原包与候选包

正式原包来自 [reproduction Release](https://github.com/ql-link/LinkRag-Eval/releases/tag/reproduction) 的 `linkrag-nevir-reproduction.zip`，而非 GitHub 自动生成的源码归档。

| 项目 | 原包 | 本次验收的候选包 |
| --- | --- | --- |
| 字节数 | 40,912,182 | 40,911,998 |
| SHA256 | `d1ac1a19a29fb302fd7901a5853a5c8179ee17f21bb32d0f86cb9e38b46b6332` | `9597f5b8eb4e1669d83baeb5d5f72e37df0731a510cef9b93839897454a32630` |

候选 ZIP 独立保留，不纳入 Git。本 PR 只提交补丁和证据；合并不会发布或替换 Release 附件。

## 审阅及应用

先用 `shasum -a 256 linkrag-nevir-reproduction.zip` 核对原包；必须与上表原包 SHA256 完全一致，不一致时停止。在新的临时目录解压，保留原 ZIP。进入解压得到的 `linkrag-nevir-reproduction/` 后执行（将补丁路径换成此仓库的实际路径）：

```bash
git apply --check /path/to/LinkRag-Eval/repro_work/reader-package-cleanup/changes.patch
git apply /path/to/LinkRag-Eval/repro_work/reader-package-cleanup/changes.patch
```

补丁已包含精确更新后的校验清单；该清单覆盖除自身外的全部 38 个文件，只有两份说明文件的摘要变化。补丁已在新的原包解压副本中实际应用，并确认全部成员字节与已验收候选 ZIP 一致，见 [补丁应用核验](verification/patch-verification.json)。

重新打包时只包含 `linkrag-nevir-reproduction/` 下的这 39 个文件，不能夹带本目录、测试输出、日志或虚拟环境。ZIP 时间戳及压缩元数据可能导致重打包摘要不同；候选包上表摘要只标识本次实际验收的 ZIP，包内字节的一致性依据为 [逐文件哈希对比](verification/file-hashes.tsv)。

## 已执行验证（2026-09-21）

在新建的独立虚拟环境中，仅安装未修改 requirements 中的 NumPy；实际为 macOS arm64、Python 3.11.15、NumPy 2.4.6。原包和从候选 ZIP 新解压的包分别运行原有单元测试及离线缓存复算，输出置于包外。下列命令用占位符表达路径，不是改写后的原始日志：

```bash
<venv>/bin/python -B -m unittest -v test_reproduction
<venv>/bin/python -B reproduce.py --output <包外独立结果目录>
```

- 两包均为 10/10 测试通过、退出码 0，复算均返回 `VERIFIED_CACHE_REPLAY`。
- 均核对 38 个包内文件及 96,572 个标量，整数精确比较，浮点绝对容差 `1e-12`，未改变校验条件。
- 三张表、两份图数据、辅助破同分结果及 `summary.json` 共 7 个科学输出逐字节一致；`verification.json` 也逐字节一致。
- 36 个受保护文件全部字节及 SHA256 一致；ZIP CRC、完整成员集合及校验表覆盖均通过。
- 单元测试的 HTTP 请求仅访问本机临时合成服务。未重新训练、召回或调用真实模型；没有重做历史 Ruff、在线数据来源或 GPU 环境检查。

证据：[核验汇总](verification/audit-results.json)、[结果哈希对比](verification/result-comparison.json)、[环境](verification/environment.json)、[原包测试](verification/original-tests.log)、[候选测试](verification/candidate-tests.log)、[原包复算](verification/original-replay.log)、[候选复算](verification/candidate-replay.log)。
