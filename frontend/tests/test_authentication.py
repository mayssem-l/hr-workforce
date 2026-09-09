from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse


class AuthenticationFlowTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="manager",
            password="valid-password-123",
        )
        self.login_url = reverse("frontend:login")
        self.logout_url = reverse("frontend:logout")

    def test_login_page_renders_and_valid_credentials_sign_user_in(self):
        response = self.client.get(self.login_url)

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "frontend/auth/login.html")
        self.assertContains(response, "<h2>Welcome back</h2>", html=True)
        self.assertContains(response, "<label for=\"id_username\">Username:</label>")
        self.assertContains(response, "<label for=\"id_password\">Password:</label>")

        response = self.client.post(
            self.login_url,
            {
                "username": "manager",
                "password": "valid-password-123",
            },
        )

        self.assertRedirects(
            response,
            reverse("frontend:landing"),
            fetch_redirect_response=False,
        )
        self.assertEqual(
            int(self.client.session["_auth_user_id"]),
            self.user.pk,
        )

    def test_invalid_login_stays_on_form_with_english_feedback(self):
        response = self.client.post(
            self.login_url,
            {
                "username": "manager",
                "password": "incorrect-password",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            "The username or password is incorrect. Please try again.",
        )
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_logout_is_post_only_and_clears_the_session(self):
        self.client.force_login(self.user)

        self.assertEqual(self.client.get(self.logout_url).status_code, 405)

        response = self.client.post(self.logout_url)

        self.assertRedirects(
            response,
            self.login_url,
            fetch_redirect_response=False,
        )
        self.assertNotIn("_auth_user_id", self.client.session)
