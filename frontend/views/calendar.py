from django.conf import settings
from django.core.paginator import Paginator
from django.http import JsonResponse
from django.shortcuts import render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_GET

from frontend.calendar_access import (
    CALENDAR_WORKSPACE_REQUIRED_MODELS,
    get_calendar_link_access,
    get_calendar_source_access,
)
from frontend.forms.calendar import (
    CalendarEventRequestForm,
    CalendarFilterForm,
    with_default_calendar_filter_state,
)
from frontend.permissions import read_models_permission_required
from frontend.presenters.calendar import (
    build_calendar_filter_context,
    build_calendar_events_response,
    build_calendar_legend_context,
    build_calendar_list_rows,
    build_calendar_source_context,
    calendar_has_narrowing_filters,
)
from frontend.selectors.calendar import (
    get_calendar_events,
    get_calendar_filter_options,
)


CALENDAR_LIST_PAGE_SIZE = 25


@read_models_permission_required(*CALENDAR_WORKSPACE_REQUIRED_MODELS)
@require_GET
def calendar_workspace(request):
    source_access = get_calendar_source_access(request.user)
    filter_options = get_calendar_filter_options()
    view_data = with_default_calendar_filter_state(
        request.GET,
        source_access=source_access,
        today=timezone.localdate(),
    )
    view_form = CalendarFilterForm(
        view_data,
        filter_options=filter_options,
        source_access=source_access,
    )
    filter_context = None
    events = ()
    event_page = None
    has_narrowing_filters = False
    if view_form.is_valid():
        filter_context = build_calendar_filter_context(
            view_form.cleaned_data,
            filter_options=filter_options,
        )
        events = get_calendar_events(
            start_date=filter_context["start_date"],
            end_date=filter_context["end_date"],
            source_access=source_access,
            filters=filter_context,
        )
        event_page = Paginator(events, CALENDAR_LIST_PAGE_SIZE).get_page(
            request.GET.get("page")
        )
        event_page.object_list = build_calendar_list_rows(
            event_page.object_list,
            link_access=get_calendar_link_access(request.user),
            filter_context=filter_context,
        )
        has_narrowing_filters = calendar_has_narrowing_filters(
            filter_context,
            source_access=source_access,
        )

    source_context = (
        build_calendar_legend_context(
            source_access,
            selected_sources=filter_context["sources"],
            events=events,
        )
        if filter_context
        else build_calendar_source_context(source_access)
    )
    calendar_filter_url = None
    calendar_event_url = None
    if filter_context:
        calendar_filter_url = (
            f"{reverse('frontend:calendar_workspace')}?"
            f"{filter_context['query_string']}"
        )
        calendar_event_url = (
            f"{reverse('frontend:calendar_events')}?"
            f"{filter_context['query_string']}"
        )
    return render(
        request,
        "frontend/calendar/workspace.html",
        {
            "breadcrumbs": [{"label": "Calendar", "url": None}],
            "view_form": view_form,
            "view_context": filter_context,
            "filter_context": filter_context,
            "event_page": event_page,
            "has_narrowing_filters": has_narrowing_filters,
            "source_context": source_context,
            "calendar_filter_url": calendar_filter_url,
            "calendar_event_url": calendar_event_url,
            "calendar_event_headers": (
                "Entry",
                "Period",
                "Status",
                "Project",
                "Employee",
                "Leave type",
                "Evidence",
            ),
            "configured_timezone": settings.TIME_ZONE,
        },
    )


@read_models_permission_required(*CALENDAR_WORKSPACE_REQUIRED_MODELS)
@require_GET
def calendar_events(request):
    source_access = get_calendar_source_access(request.user)
    filter_options = get_calendar_filter_options()
    request_data = with_default_calendar_filter_state(
        request.GET,
        source_access=source_access,
    )
    request_form = CalendarEventRequestForm(
        request_data,
        filter_options=filter_options,
        source_access=source_access,
    )
    if not request_form.is_valid():
        return JsonResponse(
            {
                "state": "invalid",
                "message": "Correct the calendar date request and try again.",
                "errors": {
                    field_name: [str(error) for error in errors]
                    for field_name, errors in request_form.errors.items()
                },
            },
            status=400,
        )

    filter_context = build_calendar_filter_context(
        request_form.cleaned_data,
        filter_options=filter_options,
    )
    link_access = get_calendar_link_access(request.user)
    events = get_calendar_events(
        start_date=filter_context["start_date"],
        end_date=filter_context["end_date"],
        source_access=source_access,
        filters=filter_context,
    )
    return JsonResponse(
        build_calendar_events_response(
            events,
            start_date=filter_context["start_date"],
            end_date=filter_context["end_date"],
            configured_timezone=settings.TIME_ZONE,
            source_access=source_access,
            link_access=link_access,
            filter_context=filter_context,
        )
    )
