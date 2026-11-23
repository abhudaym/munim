"""Analyse: answers in words, written by a local model from numbers computed here.

The model never runs SQL and never does arithmetic. Facts come from fixed queries (plus up to two
extra ones written by Ask), are computed in Python, and every number in the answer is checked
against them before it is shown.
"""

from munim.analyse.checker import unmatched_numbers
from munim.analyse.facts import Fact, Goal, fact_pack, inr
from munim.analyse.llm import AnalyseConfigError, LocalChat
from munim.analyse.service import AnalyseResult, analyse

__all__ = [
    "AnalyseConfigError",
    "AnalyseResult",
    "Fact",
    "Goal",
    "LocalChat",
    "analyse",
    "fact_pack",
    "inr",
    "unmatched_numbers",
]
