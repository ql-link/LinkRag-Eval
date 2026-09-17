# 04 — 复现入口文件收集(2026-09-18,只读)

## 齐全性
- `scripts/build_paper_reproduction.py` 第 139–143 行确认引用 `docs/papers/artifacts/` 下五个文件并附条件复制 `SELF_CHECK.md`。
- 五个文件全部存在:`README.md`、`reproduce.py`、`rerun_judge.py`、`test_reproduction.py`、`requirements.txt`;`SELF_CHECK.md` 为**已有记录**,非本轮新建。

## 敏感信息检查
- 六文件扫描(api_key/token/password/Bearer/私钥/邮箱/手机号等模式):**无真实密钥或敏感值**。
- `rerun_judge.py` 仅从 `REPRO_JUDGE_API_KEY` 环境变量读取密钥(正确模式);README/SELF_CHECK 的 "token" 均为用量口径;test 中的 `secret-` 为测试哨兵值。

## 产物
- 审阅 ZIP:`repro_work/entrypoints-review-20260918.zip`,6 个文件,文件名保留在根级,共 52,022 字节。
- 未运行脚本、未装依赖、未联网、未改原件;ZIP 保留为本地未提交产物。
