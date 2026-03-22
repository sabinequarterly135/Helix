"""Evaluation sub-package for Helix.

Provides the FitnessEvaluator pipeline orchestrator, shared models (type contracts),
template rendering with Jinja2 variable injection, template validation for variable
preservation checking, fitness aggregation with tiered weighting, regression analysis,
sampling strategies, and scoring (exact-match and behavior judge).
"""

from api.evaluation.aggregator import FitnessAggregator
from api.evaluation.evaluator import FitnessEvaluator
from api.evaluation.models import (
    CaseResult,
    EvaluationReport,
    FitnessScore,
    ValidationResult,
)
from api.evaluation.regression import (
    Regression,
    RegressionAnalyzer,
    RegressionReport,
)
from api.evaluation.renderer import TemplateRenderer, TemplateRenderError
from api.evaluation.sampling import SamplingStrategy
from api.evaluation.scorers import BehaviorJudgeScorer, ExactMatchScorer
from api.evaluation.validator import TemplateValidator

__all__ = [
    "BehaviorJudgeScorer",
    "CaseResult",
    "EvaluationReport",
    "ExactMatchScorer",
    "FitnessAggregator",
    "FitnessEvaluator",
    "FitnessScore",
    "Regression",
    "RegressionAnalyzer",
    "RegressionReport",
    "SamplingStrategy",
    "TemplateRenderError",
    "TemplateRenderer",
    "TemplateValidator",
    "ValidationResult",
]
