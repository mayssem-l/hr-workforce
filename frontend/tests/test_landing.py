from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import TestCase
from django.urls import reverse

from frontend.roles import VIEWER_GROUP, sync_role_permissions


class LandingViewTests(TestCase):
    def setUp(self):
        self.url = reverse("frontend:landing")
        sync_role_permissions()

    def test_landing_requires_authentication(self):
        response = self.client.get(self.url)

        self.assertRedirects(
            response,
            f"{reverse('frontend:login')}?next={self.url}",
            fetch_redirect_response=False,
        )

    def test_authenticated_user_without_read_permission_is_forbidden(self):
        user = get_user_model().objects.create_user(username="unassigned")
        self.client.force_login(user)

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 403)

    def test_viewer_can_render_landing_template(self):
        user = get_user_model().objects.create_user(username="viewer")
        user.groups.add(Group.objects.get(name=VIEWER_GROUP))
        self.client.force_login(user)

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "frontend/dashboard/landing.html")
        self.assertContains(
            response,
            "<h1>Workforce overview</h1>",
            html=True,
        )
        self.assertContains(response, "viewer")
        self.assertContains(response, "Sign out")
