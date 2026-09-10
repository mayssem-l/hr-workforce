from time import perf_counter

from core.services.optimization import (
    build_recommendation_explanations,
    compare_recommendations,
    find_all_feasible_teams,
    find_pareto_teams,
    select_recommended_teams,
)


def run_recommendation_pipeline(project):
    """Run the existing deterministic recommendation pipeline in order."""

    started_at = perf_counter()
    feasible_teams = find_all_feasible_teams(project)
    pareto_teams = find_pareto_teams(feasible_teams)
    recommendations = select_recommended_teams(pareto_teams)
    comparisons = compare_recommendations(recommendations)
    explanations = build_recommendation_explanations(
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
