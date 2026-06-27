"""指标实现与注册表。指标全部是纯函数(async 仅为协议签名统一),零 IO、可单测。"""

from linkrag_eval.metrics.registry import metrics_for, register

__all__ = ["metrics_for", "register"]
