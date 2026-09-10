import json

# from openai import OpenAI

from google import genai
from google.genai import types

# client = OpenAI()


def generate_manager_summary(explanation, *, timeout_ms=2500):
    """
    Generate a short manager-friendly explanation
    from deterministic recommendation facts.

    The LLM does not calculate, rank, or select teams.
    """
    # client = OpenAI()
    client = genai.Client(
        http_options=types.HttpOptions(
            timeout=timeout_ms,
            retry_options=types.HttpRetryOptions(attempts=1),
        )
    )

    payload = {
        "category": explanation["category"],
        "label": explanation["label"],
        "team": [
            str(employee)
            for employee in explanation["team"]
        ],
        "strengths": explanation["strengths"],
        "tradeoffs": explanation["tradeoffs"],
    }

    instructions = """
You explain the results of an HR workforce planning
decision-support system to a manager.

The calculations, team selection, metrics, strengths,
and trade-offs have already been determined by Python.

Mandatory rules:
- Write only in English.
- Do not recalculate any value.
- Do not invent any information.
- Do not modify any number.
- Do not rank individual employees.
- Do not recommend or exclude an employee yourself.
- Use only the facts provided in the input.
- Write 1 or 2 short sentences maximum.
- Use clear, professional, manager-friendly language.
- Explain mainly when this team alternative may be useful.
"""

    # response = client.responses.create(
    #     model="gpt-5.6-luna",
    #     instructions=instructions,
    #     input=json.dumps(
    #         payload,
    #         ensure_ascii=False,
    #     ),
    # )

    response = client.models.generate_content(
        model="gemini-3.5-flash-lite",
        contents=json.dumps(
            payload,
            ensure_ascii=False,
        ),
        config=types.GenerateContentConfig(
            system_instruction=instructions,
            temperature=0.2,
        ),
    )

    return response.text.strip()


def generate_manager_summaries(explanations, *, timeout_ms=2500):
    """
    Generate summaries for ALL recommendations.
    """

    results = []

    for explanation in explanations:

        enriched_explanation = explanation.copy()

        enriched_explanation["manager_summary"] = (
            generate_manager_summary(
                explanation,
                timeout_ms=timeout_ms,
            )
        )

        results.append(enriched_explanation)

    return results
