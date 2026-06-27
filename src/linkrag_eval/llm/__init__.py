"""eval 自带的轻量模型调用层(config 驱动,模型可选)。

为什么 eval 自持:生产把"系统配置 sparse 工厂"删了(只剩 per-user,读用户配置表,在黑名单内),
judge 也早已解耦(eval_llm)。本层统一承载 eval 的对外模型调用——sparse 编码、judge,后续可纳
dense——全部纯 httpx + EVAL_ 配置,不依赖 rag 的 provider/ModelFactory,零 rag import。
"""
