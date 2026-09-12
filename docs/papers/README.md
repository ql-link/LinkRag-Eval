# 论文全文与写作目录

本目录根层的参考文献 PDF 仅用于本地科研复核，不进入 Git 版本库，也不随公开 PR 分发。

可核验的题名、DOI、证据边界和本地文件名映射统一维护在
[`robust-fusion-literature.md`](../plans/robust-fusion-literature.md)。需要复核全文时，研究成员应按 DOI
从有权访问的正式来源自行获取，并使用文献地图中约定的文件名放入本目录。

本项目的论文工作稿位于 [`manuscript/`](manuscript/README.md)，唯一 PDF 为 [`manuscript/paper.pdf`](manuscript/paper.pdf)。后续在同一份源码上修改并覆盖生成该 PDF；LaTeX、BibTeX、PDF、编译入口和写作说明均纳入 Git，历史版本通过 Git 追溯。编译辅助文件保留在本地 `manuscript/build/`。当前工作稿包含六页 short paper 的引言、设置、方法与列表诊断。
