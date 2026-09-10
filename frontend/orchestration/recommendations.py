from time import perf_counter

from core.services.optimization import (
    build_recommendation_explanations,
    compare_recommendations,
    find_all_feasible_teams,
    find_pareto_teams,
    select_recommended_teams,
)


class RecommendationPipelineStageError(RuntimeError):
    """Contain a backend-stage failure without exposing its exception details."""

    def __init__(self, stage):
        self.stage = stage
        super().__init__(stage)


def _run_stage(stage, function, *args):
    try:
        return function(*args)
    except Exception as exc:
        raise RecommendationPipelineStageError(stage) from exc


def run_recommendation_pipeline(project):
    """Run the existing deterministic recommendation pipeline in order."""

    started_at = perf_counter()
    feasible_teams = _run_stage(
        "team_assessment",
        find_all_feasible_teams,
        project,
    )
    pareto_teams = _run_stage(
        "comparison_filter",
        find_pareto_teams,
        feasible_teams,
    )
    recommendations = _run_stage(
        "recommendation_selection",
        select_recommended_teams,
        pareto_teams,
    )
    comparisons = _run_stage(
        "strategy_comparison",
        compare_recommendations,
        recommendations,
    )
    explanations = _run_stage(
        "deterministic_evidence",
        build_recommendation_explanations,
        recommendations,
        comparisons,
    )
    elapsed_seconds = perf_counter() - started_at

    return {
        "feasible_teams": feasible_teams,
        "pareto_teams": pareto_teams,
        "recommendations": recommendations,
        "comparisons": comparisons,
        "explanations": explanations,
        "elapsed_seconds": elapsed_seconds,
    }
