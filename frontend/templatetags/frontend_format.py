from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from django import forms, template
from django.utils import formats


register = template.Library()

EMPTY_VALUE = "—"

STATUS_TONES = {
    "active": "status-badge--success",
    "approved": "status-badge--success",
    "completed": "status-badge--success",
    "present": "status-badge--success",
    "planned": "status-badge--info",
    "in_progress": "status-badge--info",
    "remote": "status-badge--info",
    "pending": "status-badge--warning",
    "on_hold": "status-badge--warning",
    "on_leave": "status-badge--warning",
    "late": "status-badge--warning",
    "inactive": "status-badge--danger",
    "cancelled": "status-badge--danger",
    "rejected": "status-badge--danger",
    "absent": "status-badge--danger",
}


def _decimal_value(value):
    if value in (None, ""):
        return None

    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None


@register.filter
def workforce_date(value):
    """Format dates consistently across workforce-facing screens."""
    if value in (None, ""):
        return EMPTY_VALUE

    try:
        return formats.date_format(value, "M j, Y")
    except (AttributeError, TypeError, ValueError):
        return EMPTY_VALUE


@register.filter
def decimal_hours(value):
    """Display decimal effort and capacity values with two decimal places."""
    number = _decimal_value(value)
    if number is None or not number.is_finite():
        return EMPTY_VALUE

    rounded = number.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return f"{rounded:,.2f} h"


@register.filter
def percentage(value):
    """Display an already-calculated percentage without recalculating it."""
    number = _decimal_value(value)
    if number is None or not number.is_finite():
        return EMPTY_VALUE

    rounded = number.quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)
    return f"{rounded:,.1f}%"


@register.filter
def status_label(value):
    """Turn stored status values into consistent English display labels."""
    if value in (None, ""):
        return EMPTY_VALUE

    choice_label = getattr(value, "label", None)
    if choice_label:
        return str(choice_label)

    normalized = str(value).strip().replace("-", " ").replace("_", " ")
    return normalized[:1].upper() + normalized[1:].lower()


@register.filter
def status_badge_class(value):
    """Map known statuses to an accessible, presentation-only badge tone."""
    normalized = str(value or "").strip().lower().replace("-", "_")
    return STATUS_TONES.get(normalized, "status-badge--neutral")


@register.filter
def message_alert_class(tags):
    """Translate Django message levels to theme alert classes."""
    tag_set = set(str(tags or "").split())
    if "error" in tag_set:
        return "app-alert--danger"
    if "warning" in tag_set:
        return "app-alert--warning"
    if "success" in tag_set:
        return "app-alert--success"
    return "app-alert--info"


@register.filter
def form_control(bound_field):
    """Render a bound field with the appropriate Bootstrap control class."""
    widget = bound_field.field.widget
    if isinstance(widget, forms.CheckboxInput):
        control_class = "form-check-input"
    elif isinstance(widget, (forms.Select, forms.SelectMultiple)):
        control_class = "form-select"
    else:
        control_class = "form-control"

    attrs = widget.attrs.copy()
    attrs["class"] = " ".join(
        part for part in (attrs.get("class", ""), control_class) if part
    )
    if bound_field.errors:
        attrs["aria-invalid"] = "true"
    return bound_field.as_widget(attrs=attrs)
