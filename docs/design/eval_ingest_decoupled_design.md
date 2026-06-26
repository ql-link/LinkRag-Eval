# 评测灌库解耦设计（已合并，见权威稿）

> ⚠️ **本文已合并进 [eval_storage_design.md](eval_storage_design.md)（权威稿 §一/§五/§六/§七）。**
> 解耦灌库（不走 `ParseTaskPipeline`、只调 core 组件）、完整数据足迹隔离表、`Chunk→可索引对象`
> 适配、`ChunkContentResolver` 缝、lockstep 护栏均迁至权威稿。本文保留为指针，勿再据此实现。
