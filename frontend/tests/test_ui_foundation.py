import re
from datetime import date
from decimal import Decimal
from pathlib import Path

from django import forms
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.contrib.staticfiles import finders
from django.core.paginator import Paginator
from django.template import Context, Template
from django.template.loader import render_to_string
from django.test import RequestFactory, SimpleTestCase, TestCase
from django.urls import reverse

from frontend.roles import VIEWER_GROUP, sync_role_permissions


class InterfaceFoundationTests(TestCase):
    def setUp(self):
        sync_role_permissions()
        self.user = get_user_model().objects.create_user(username="viewer")
        self.user.groups.add(Group.objects.get(name=VIEWER_GROUP))
        self.client.force_login(self.user)

    def test_authenticated_shell_renders_local_assets_and_primary_navigation(self):
        response = self.client.get(reverse("frontend:landing"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            '/static/frontend/vendor/bootstrap-5.3.8.min.css',
        )
        self.assertContains(
            response,
            '/static/frontend/vendor/bootstrap-5.3.8.bundle.min.js',
        )
        self.assertContains(response, '/static/frontend/css/theme.css')
        self.assertContains(response, '<a class="skip-link" href="#main-content">')
        self.assertContains(response, 'aria-label="Primary navigation"')
        self.assertContains(response, 'aria-label="Breadcrumb"')
        self.assertContains(response, 'aria-current="page"')
        for area in (
            "Dashboard",
            "Workforce",
            "Projects",
            "Planning",
            "Recommendations",
        ):
            with self.subTest(area=area):
                self.assertContains(response, area)

    def test_messages_area_renders_accessible_english_feedback(self):
        request = RequestFactory().get("/")
        request.user = self.user
        SessionMiddleware(lambda current_request: None).process_request(request)
        MessageMiddleware(lambda current_request: None).process_request(request)
        messages.success(request, "Planning update saved.")

        rendered = render_to_string(
            "frontend/components/messages.html",
            request=request,
        )

        self.assertIn('aria-live="polite"', rendered)
        self.assertIn('role="status"', rendered)
        self.assertIn("Planning update saved.", rendered)
        self.assertIn('aria-label="Close message"', rendered)

    def test_shell_keeps_keyboard_navigation_native_and_heading_order_semantic(self):
        response = self.client.get(reverse("frontend:landing"))
        rendered = response.content.decode("utf-8")

        self.assertIn('type="button" data-bs-toggle="offcanvas"', rendered)
        self.assertIn('aria-controls="mobile-navigation"', rendered)
        self.assertIn('type="submit"', rendered)
        self.assertNotRegex(rendered, r'tabindex="[1-9][0-9]*"')
        self.assertLess(rendered.index("<h1>"), rendered.index("<h2"))


class SharedComponentTests(SimpleTestCase):
    class EffortForm(forms.Form):
        effort = forms.DecimalField(
            label="Planned effort",
            help_text="Enter effort in decimal hours.",
        )

    def test_form_field_has_label_help_and_validation_associations(self):
        form = self.EffortForm(data={"effort": ""})
        self.assertFalse(form.is_valid())

        rendered = render_to_string(
            "frontend/components/form_field.html",
            {"field": form["effort"]},
        )

        self.assertIn('<label for="id_effort">Planned effort:</label>', rendered)
        self.assertIn('class="form-control"', rendered)
        self.assertIn('aria-invalid="true"', rendered)
        self.assertIn('id="id_effort_helptext"', rendered)
        self.assertIn('id="id_effort_error"', rendered)
        self.assertIn(
            'aria-describedby="id_effort_helptext id_effort_error"',
            rendered,
        )
        self.assertIn("This field is required.", rendered)

    def test_table_renders_headers_rows_and_empty_fallback(self):
        rendered = render_to_string(
            "frontend/components/table.html",
            {
                "caption": "Available employees",
                "headers": ["Employee", "Capacity"],
                "rows": [["Alex Morgan", "12.00 h"]],
            },
        )
        empty_rendered = render_to_string(
            "frontend/components/table.html",
            {"headers": ["Employee"], "rows": []},
        )

        self.assertIn("<caption>Available employees</caption>", rendered)
        self.assertIn('<th scope="col">Employee</th>', rendered)
        self.assertIn("Alex Morgan", rendered)
        self.assertIn("No records to display.", empty_rendered)

    def test_pagination_preserves_existing_query_parameters(self):
        request = RequestFactory().get("/workforce/?status=active")
        page_obj = Paginator(list(range(25)), 10).get_page(2)

        rendered = render_to_string(
            "frontend/components/pagination.html",
            {"page_obj": page_obj},
            request=request,
        )

        self.assertIn('aria-label="Results pages"', rendered)
        self.assertIn("Page 2 of 3", rendered)
        self.assertIn("status=active&amp;page=1", rendered)
        self.assertIn('aria-current="page">2</span>', rendered)

    def test_status_badge_and_all_state_components_render_semantics(self):
        badge = render_to_string(
            "frontend/components/status_badge.html",
            {"status": "in_progress"},
        )
        confirmation = render_to_string(
            "frontend/components/confirmation_state.html",
            {"title": "Confirm assignment", "message": "Review this change."},
        )
        loading = render_to_string("frontend/components/loading_state.html")
        empty = render_to_string("frontend/components/empty_state.html")
        error = render_to_string("frontend/components/error_state.html")

        self.assertIn("status-badge--info", badge)
        self.assertIn("In progress", badge)
        self.assertIn('role="alert"', confirmation)
        self.assertIn("Confirm assignment", confirmation)
        self.assertIn('role="status"', loading)
        self.assertIn('aria-live="polite"', loading)
        self.assertIn("Nothing here yet", empty)
        self.assertIn('role="alert"', error)


class PresentationFormatterTests(SimpleTestCase):
    def render_filter(self, filter_name, value):
        source = "{% load frontend_format %}{{ value|" + filter_name + " }}"
        return Template(source).render(Context({"value": value}))

    def test_dates_hours_percentages_and_statuses_have_consistent_output(self):
        self.assertEqual(
            self.render_filter("workforce_date", date(2026, 9, 8)),
            "Sep 8, 2026",
        )
        self.assertEqual(
            self.render_filter("decimal_hours", Decimal("1234.5")),
            "1,234.50 h",
        )
        self.assertEqual(
            self.render_filter("percentage", Decimal("37.45")),
            "37.5%",
        )
        self.assertEqual(
            self.render_filter("status_label", "in_progress"),
            "In progress",
        )

    def test_empty_and_invalid_numeric_values_use_a_clear_placeholder(self):
        self.assertEqual(self.render_filter("workforce_date", None), "—")
        self.assertEqual(self.render_filter("decimal_hours", "not-a-number"), "—")
        self.assertEqual(self.render_filter("percentage", None), "—")


class StaticAssetAndAccessibilityTests(SimpleTestCase):
    ACCESSIBLE_COLOR_PAIRS = (
        ("--wf-navy-950", "#ffffff"),
        ("--wf-teal-700", "#ffffff"),
        ("--wf-ink-600", "#ffffff"),
        ("--wf-success", "--wf-success-bg"),
        ("--wf-info", "--wf-info-bg"),
        ("--wf-warning", "--wf-warning-bg"),
        ("--wf-danger", "--wf-danger-bg"),
        ("--wf-ink-700", "#edf1f5"),
    )

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.theme_path = Path(finders.find("frontend/css/theme.css"))
        cls.theme = cls.theme_path.read_text(encoding="utf-8")

    def test_bootstrap_distribution_is_locally_pinned_with_its_license(self):
        css_path = Path(finders.find("frontend/vendor/bootstrap-5.3.8.min.css"))
        js_path = Path(
            finders.find("frontend/vendor/bootstrap-5.3.8.bundle.min.js")
        )
        license_path = Path(
            finders.find("frontend/vendor/BOOTSTRAP-LICENSE.txt")
        )

        self.assertRegex(
            css_path.read_text(encoding="utf-8")[:300],
            r"Bootstrap\s+v5\.3\.8",
        )
        self.assertRegex(
            js_path.read_text(encoding="utf-8")[:300],
            r"Bootstrap\s+v5\.3\.8",
        )
        self.assertIn("The MIT License", license_path.read_text(encoding="utf-8"))

    def test_theme_defines_visible_focus_and_reduced_motion_behavior(self):
        self.assertIn(":focus-visible", self.theme)
        self.assertIn("outline: 3px solid var(--wf-focus)", self.theme)
        self.assertIn("@media (prefers-reduced-motion: reduce)", self.theme)
        self.assertIn("@media (min-width: 992px)", self.theme)
        self.assertIn("@media (max-width: 575.98px)", self.theme)

    def test_key_text_and_status_color_pairs_meet_wcag_aa(self):
        variables = dict(
            re.findall(r"(--[a-z0-9-]+):\s*(#[0-9a-f]{6})", self.theme)
        )

        for foreground, background in self.ACCESSIBLE_COLOR_PAIRS:
            foreground_hex = variables.get(foreground, foreground)
            background_hex = variables.get(background, background)
            with self.subTest(foreground=foreground, background=background):
                self.assertGreaterEqual(
                    self._contrast_ratio(foreground_hex, background_hex),
                    4.5,
                )

    @classmethod
    def _contrast_ratio(cls, first, second):
        brighter, darker = sorted(
            (cls._relative_luminance(first), cls._relative_luminance(second)),
            reverse=True,
        )
        return (brighter + 0.05) / (darker + 0.05)

    @staticmethod
    def _relative_luminance(hex_color):
        channels = [
            int(hex_color[index : index + 2], 16) / 255
            for index in (1, 3, 5)
        ]
        linear = [
            channel / 12.92
            if channel <= 0.04045
            else ((channel + 0.055) / 1.055) ** 2.4
            for channel in channels
        ]
        return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]
