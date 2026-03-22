"""Tests for evaluation shared models: CaseResult, FitnessScore, EvaluationReport, ValidationResult."""

from api.evaluation.models import (
    CaseResult,
    EvaluationReport,
    FitnessScore,
    ValidationResult,
)


class TestCaseResult:
    """Test CaseResult model creation, defaults, and serialization."""

    def test_create_with_required_fields(self):
        result = CaseResult(case_id="case-1", score=0.85)
        assert result.case_id == "case-1"
        assert result.score == 0.85

    def test_default_values(self):
        result = CaseResult(case_id="case-1", score=0.5)
        assert result.tier == "normal"
        assert result.passed is False
        assert result.reason == ""
        assert result.expected is None
        assert result.actual_content is None
        assert result.actual_tool_calls is None

    def test_create_with_all_fields(self):
        result = CaseResult(
            case_id="case-2",
            tier="critical",
            score=1.0,
            passed=True,
            reason="Exact match",
            expected={"response": "hello"},
            actual_content="hello",
            actual_tool_calls=[{"name": "greet", "args": {}}],
        )
        assert result.tier == "critical"
        assert result.passed is True
        assert result.reason == "Exact match"
        assert result.expected == {"response": "hello"}
        assert result.actual_content == "hello"
        assert result.actual_tool_calls == [{"name": "greet", "args": {}}]

    def test_json_round_trip(self):
        original = CaseResult(
            case_id="case-rt",
            tier="low",
            score=0.3,
            passed=False,
            reason="Partial match",
            expected={"key": "value"},
            actual_content="some content",
        )
        json_str = original.model_dump_json()
        restored = CaseResult.model_validate_json(json_str)
        assert restored == original

    def test_tier_string_values(self):
        """CaseResult.tier accepts string values: critical, normal, low."""
        for tier in ("critical", "normal", "low"):
            result = CaseResult(case_id="t", score=0.0, tier=tier)
            assert result.tier == tier


class TestFitnessScore:
    """Test FitnessScore model creation, defaults, and serialization."""

    def test_create_with_score(self):
        fitness = FitnessScore(score=0.75)
        assert fitness.score == 0.75

    def test_default_values(self):
        fitness = FitnessScore(score=0.0)
        assert fitness.rejected is False
        assert fitness.rejection_reason is None
        assert fitness.case_results == []

    def test_rejected_fitness(self):
        fitness = FitnessScore(
            score=0.0,
            rejected=True,
            rejection_reason="Missing critical variable",
        )
        assert fitness.rejected is True
        assert fitness.rejection_reason == "Missing critical variable"

    def test_with_case_results(self):
        cases = [
            CaseResult(case_id="c1", score=1.0, passed=True),
            CaseResult(case_id="c2", score=0.0, passed=False),
        ]
        fitness = FitnessScore(score=0.5, case_results=cases)
        assert len(fitness.case_results) == 2
        assert fitness.case_results[0].case_id == "c1"

    def test_json_round_trip(self):
        original = FitnessScore(
            score=0.8,
            rejected=False,
            case_results=[CaseResult(case_id="c1", score=0.8, passed=True)],
        )
        json_str = original.model_dump_json()
        restored = FitnessScore.model_validate_json(json_str)
        assert restored == original


class TestEvaluationReport:
    """Test EvaluationReport model creation and serialization."""

    def test_create_report(self):
        fitness = FitnessScore(score=0.9)
        cases = [CaseResult(case_id="c1", score=0.9, passed=True)]
        report = EvaluationReport(
            fitness=fitness,
            case_results=cases,
            total_cases=1,
        )
        assert report.fitness.score == 0.9
        assert report.total_cases == 1
        assert report.cost_summary == {}

    def test_with_cost_summary(self):
        report = EvaluationReport(
            fitness=FitnessScore(score=0.5),
            case_results=[],
            total_cases=0,
            cost_summary={"total_usd": 0.05, "calls": 10},
        )
        assert report.cost_summary["total_usd"] == 0.05

    def test_json_round_trip(self):
        original = EvaluationReport(
            fitness=FitnessScore(score=0.7, case_results=[]),
            case_results=[CaseResult(case_id="c1", score=0.7)],
            total_cases=1,
            cost_summary={"total_usd": 0.01},
        )
        json_str = original.model_dump_json()
        restored = EvaluationReport.model_validate_json(json_str)
        assert restored == original


class TestValidationResult:
    """Test ValidationResult model creation, defaults, and serialization."""

    def test_valid_result(self):
        result = ValidationResult(valid=True)
        assert result.valid is True
        assert result.missing_variables == []
        assert result.original_variables == []
        assert result.evolved_variables == []

    def test_invalid_result_with_missing(self):
        result = ValidationResult(
            valid=False,
            missing_variables=["name", "age"],
            original_variables=["name", "age", "role"],
            evolved_variables=["role"],
        )
        assert result.valid is False
        assert result.missing_variables == ["name", "age"]

    def test_json_round_trip(self):
        original = ValidationResult(
            valid=False,
            missing_variables=["x"],
            original_variables=["x", "y"],
            evolved_variables=["y"],
        )
        json_str = original.model_dump_json()
        restored = ValidationResult.model_validate_json(json_str)
        assert restored == original
