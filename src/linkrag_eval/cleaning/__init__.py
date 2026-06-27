"""CLEANING 层:渲染件经生产 parser 清洗回 md,与参考 md 纯函数比对。

被测对象是生产 ``ParserFactory``(解析/清洗那一步),故 ``adapter.py`` 是允许 import rag
的 adapter 之一;指标计算在 ``metrics/cleaning.py``(纯函数),编排在
``runners/cleaning_runner.py``。
"""
