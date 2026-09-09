from itertools import groupby


def group_skills_by_category(skills):
    """Shape an ordered page of skills into stable category sections."""
    groups = []
    for category, category_skills in groupby(
        skills,
        key=lambda skill: skill.category,
    ):
        grouped_skills = list(category_skills)
        groups.append(
            {
                "category": category,
                "skills": grouped_skills,
                "skill_count": len(grouped_skills),
            }
        )
    return groups
