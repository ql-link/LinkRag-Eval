# 01 — 工作版本上下文(2026-09-18)

## 仓库状态
- 根目录:`/Users/kawauso/Documents/Projects/LinkRag-Eval`;分支 `master`;HEAD `7578d34510bef750d7b0f04a7bde8518f29fccbd`。
- 未提交修改:`M docs/papers/README.md`、`M docs/plans/robust-fusion-literature.md`;未跟踪 `scripts/build_paper_reproduction.py`(NevIR 复现包构建脚本,声明不触碰 manuscript,非论文构建入口)。

## 论文构建入口与产物
- 构建入口:`docs/papers/manuscript/Makefile`(`make` → `latexmk -pdf -jobname=paper -outdir=build main.tex` → `mv build/paper.pdf paper.pdf`)。
- 主 TeX:`docs/papers/manuscript/main.tex`(\input 各章节 tex);参考文献:`docs/papers/manuscript/references.bib`。
- 在版 PDF:`docs/papers/manuscript/paper.pdf`。
- 判定依据:Makefile 是目录内唯一构建规则,`paper.pdf` 由其声明目标产出;全仓仅此一份论文 PDF(其余 *.pdf 均为 `.agents/skills` 测试夹具);`artifacts/SHA256SUMS` 不含 paper.pdf 条目。无候选歧义。
- `manuscript/` 整目录被 `.gitignore:158`(`/docs/papers/*`)排除,故论文文件不出现于 git status。
- SHA256:`af5ebe0aac86c1cc2de3dbaacc0ce71ee7fb3956077283f63a626f01fa6e55bd`(251,223 字节,6 页)。

## Worktree(已清理;`git worktree list` 现仅主仓)
- 论文版本权威:以主仓 `LinkRag-Eval/docs/papers/manuscript/` 为唯一准,其他 worktree 的手稿不作依据。
- 已删:`../LinkRag-Eval-issue22-completion`(detached `a6e2cc7`,干净且已并入 master)。
- 已删(--force):`../LinkRag-Eval-paper-local`;其未提交 manuscript 为 09-14 旧版(旧关键词/旧 hyperref),无独有文件;分支 `codex/paper-updates-20260914` 保留,提交未失。
- 已 `git worktree prune` 清掉 3 个目录本已不存在的 prunable 记录(`linkrag-pr-delivery-20260912`、`linkrag-issue21-pr-20260913`、`linkrag-issue22-review-20260913`)。
- 另:`../LinkRag-Eval-restructure-backups` 为普通目录,非本仓 worktree,未动。
