"""报告渲染:HTML(人读)与 JSON(机器读,趋势/基线消费)。"""

from linkrag_eval.reporters.base import RegressionCriteria, diff_metrics
from linkrag_eval.reporters.cleaning_reporter import CleaningHtmlReporter
from linkrag_eval.reporters.emit import (
    write_cleaning_reports,
    write_retrieval_reports,
)
from linkrag_eval.reporters.html_reporter import HtmlReporter
from linkrag_eval.reporters.json_reporter import JsonReporter

__all__ = [
    "RegressionCriteria",
    "diff_metrics",
    "CleaningHtmlReporter",
    "HtmlReporter",
    "JsonReporter",
    "write_cleaning_reports",
    "write_retrieval_reports",
]
