import statistics
import time
from pathlib import Path

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.contrib.staticfiles import finders
from django.db import connection
from django.template.loader import get_template
from django.test import Client, SimpleTestCase, TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import resolve, reverse

from frontend.roles import VIEWER_GROUP, sync_role_permissions


class FrontendRouteContractTests(SimpleTestCase):
    ROUTES = (
        ("frontend:landing", "/"),
        ("frontend:login", "/login/"),
        ("frontend:logout", "/logout/"),
    )

    def test_namespaced_route_names_reverse_and_resolve(self):
        for route_name, expected_path in self.ROUTES:
            with self.subTest(route_name=route_name):
                self.assertEqual(reverse(route_name), expected_path)

                match = resolve(expected_path)
                self.assertEqual(match.view_name, route_name)
                self.assertEqual(match.app_name, "frontend")
                self.assertEqual(match.namespace, "frontend")


class TemplateAndStaticVerificationTests(SimpleTestCase):
    TEMPLATES = (
        "frontend/base.html",
        "frontend/auth/login.html",
        "frontend/dashboard/landing.html",
        "frontend/components/brand.html",
        "frontend/components/navigation.html",
        "frontend/components/breadcrumbs.html",
        "frontend/components/page_header.html",
        "frontend/components/messages.html",
        "frontend/components/form_field.html",
        "frontend/components/table.html",
        "frontend/components/pagination.html",
        "frontend/components/status_badge.html",
        "frontend/components/confirmation_state.html",
        "frontend/components/loading_state.html",
        "frontend/components/empty_state.html",
        "frontend/components/error_state.html",
    )
    STATIC_ASSETS = (
        "frontend/css/theme.css",
        "frontend/js/app.js",
        "frontend/vendor/bootstrap-5.3.8.min.css",
        "frontend/vendor/bootstrap-5.3.8.bundle.min.js",
        "frontend/vendor/BOOTSTRAP-LICENSE.txt",
    )

    def test_all_foundation_templates_compile(self):
        for template_name in self.TEMPLATES:
            with self.subTest(template_name=template_name):
                self.assertIsNotNone(get_template(template_name))

    def test_all_foundation_static_assets_are_discoverable_and_nonempty(self):
        for asset_name in self.STATIC_ASSETS:
            with self.subTest(asset_name=asset_name):
                asset_path = finders.find(asset_name)
                self.assertIsNotNone(asset_path)
                self.assertGreater(Path(asset_path).stat().st_size, 0)


class InitialPagePerformanceBaselineTests(TestCase):
    SAMPLE_COUNT = 25
    LOGIN_QUERY_COUNT = 0
    LANDING_QUERY_COUNT = 5

    @classmethod
    def setUpTestData(cls):
        sync_role_permissions()
        cls.viewer = get_user_model().objects.create_user(username="baseline-viewer")
        cls.viewer.groups.add(Group.objects.get(name=VIEWER_GROUP))

    def test_initial_page_query_counts(self):
        anonymous_client = Client()
        with self.assertNumQueries(self.LOGIN_QUERY_COUNT):
            login_response = anonymous_client.get(reverse("frontend:login"))

        self.client.force_login(self.viewer)
        with self.assertNumQueries(self.LANDING_QUERY_COUNT):
            landing_response = self.client.get(reverse("frontend:landing"))

        self.assertEqual(login_response.status_code, 200)
        self.assertEqual(landing_response.status_code, 200)

    def test_initial_page_response_time_baseline(self):
        anonymous_client = Client()
        login_result = self._measure_requests(
            anonymous_client,
            reverse("frontend:login"),
            self.LOGIN_QUERY_COUNT,
        )

        self.client.force_login(self.viewer)
        landing_result = self._measure_requests(
            self.client,
            reverse("frontend:landing"),
            self.LANDING_QUERY_COUNT,
        )

        print(
            "\nM1.6 initial-page baseline "
            f"({self.SAMPLE_COUNT} warm Django test-client GETs per page):\n"
            f"  login:   queries={self.LOGIN_QUERY_COUNT}, "
            f"median={login_result['median_ms']:.3f} ms, "
            f"p95={login_result['p95_ms']:.3f} ms, "
            f"min={login_result['min_ms']:.3f} ms, "
            f"max={login_result['max_ms']:.3f} ms\n"
            f"  landing: queries={self.LANDING_QUERY_COUNT}, "
            f"median={landing_result['median_ms']:.3f} ms, "
            f"p95={landing_result['p95_ms']:.3f} ms, "
            f"min={landing_result['min_ms']:.3f} ms, "
            f"max={landing_result['max_ms']:.3f} ms"
        )

    def _measure_requests(self, client, url, expected_queries):
        warmup_response = client.get(url)
        self.assertEqual(warmup_response.status_code, 200)

        durations_ms = []
        for _ in range(self.SAMPLE_COUNT):
            with CaptureQueriesContext(connection) as captured_queries:
                started_at = time.perf_counter()
                response = client.get(url)
                durations_ms.append((time.perf_counter() - started_at) * 1000)

            self.assertEqual(response.status_code, 200)
            self.assertEqual(len(captured_queries), expected_queries)

        return {
            "median_ms": statistics.median(durations_ms),
            "p95_ms": statistics.quantiles(
                durations_ms,
                n=20,
                method="inclusive",
            )[18],
            "min_ms": min(durations_ms),
            "max_ms": max(durations_ms),
        }
