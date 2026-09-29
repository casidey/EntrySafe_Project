from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from .models import UserSettings


class ThemeAndSettingsTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("res", password="x")
        self.client.force_login(self.user)
        self.url = reverse("user_settings:settings")

    def test_light_by_default(self):
        self.assertContains(self.client.get(reverse("home:home")), 'data-theme="light"')

    def test_dark_mode_setting_is_rendered_on_every_page(self):
        UserSettings.objects.create(user=self.user, dark_mode=True)
        for name in ("home:home", "profile:profile", "user_settings:settings"):
            self.assertContains(self.client.get(reverse(name)), 'data-theme="dark"')

    def test_ajax_autosave_toggles_dark_mode(self):
        r = self.client.post(self.url, {"dark_mode": "on", "email_notifications": "on"},
                             headers={"X-Requested-With": "XMLHttpRequest"})
        self.assertEqual(r.json(), {"ok": True, "dark_mode": True})
        self.assertTrue(UserSettings.objects.get(user=self.user).dark_mode)
        r = self.client.post(self.url, {"email_notifications": "on"}, headers={"X-Requested-With": "XMLHttpRequest"})
        self.assertFalse(r.json()["dark_mode"])

    def test_plain_post_still_redirects(self):
        self.assertRedirects(self.client.post(self.url, {"dark_mode": "on"}), self.url)

    def test_anonymous_pages_have_no_server_theme(self):
        self.client.logout()
        self.assertContains(self.client.get(reverse("login:login")), 'data-theme=""')
