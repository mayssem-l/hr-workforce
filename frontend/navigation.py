from urllib.parse import urlencode, urlsplit

from django.urls import Resolver404, resolve, reverse

from core.models import Project


PLANNING_RETURN_PARAMETER = "return_to"


def get_planning_return_url(request, *, project_id=None):
    """Return an allow-listed planning workspace path from the query string."""

    candidate = request.GET.get(PLANNING_RETURN_PARAMETER, "")
    if not candidate or len(candidate) > 2048:
        return None

    parts = urlsplit(candidate)
    if (
        parts.scheme
        or parts.netloc
        or parts.query
        or parts.fragment
        or not parts.path.startswith("/")
    ):
        return None

    try:
        match = resolve(parts.path)
    except Resolver404:
        return None
    if match.view_name != "frontend:project_planning":
        return None

    return_project_id = match.kwargs.get("project_id")
    if project_id is not None and return_project_id != project_id:
        return None
    if not Project.objects.filter(project_id=return_project_id).exists():
        return None

    return reverse(
        "frontend:project_planning",
        args=[return_project_id],
    )


def with_planning_return(url, planning_url):
    """Add the single supported return parameter to a destination URL."""

    if not planning_url:
        return url
    separator = "&" if "?" in url else "?"
    return f"{url}{separator}{urlencode({PLANNING_RETURN_PARAMETER: planning_url})}"


def planning_return_query(planning_url):
    if not planning_url:
        return ""
    return urlencode({PLANNING_RETURN_PARAMETER: planning_url})
