from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from apps.guard import services as gate
from apps.profile.models import UserProfile
from apps.restrictions import services

from .models import Notification


class NotificationFeedTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user("boss", password="x", is_staff=True)
        self.resident = User.objects.create_user("res", password="x")
        UserProfile.objects.create(user=self.resident, full_name="Rita", approval_status="APPROVED")
        self.other = User.objects.create_user("res2", password="x")
        UserProfile.objects.create(user=self.other, full_name="Olga", approval_status="APPROVED")
        self.guard = User.objects.create_user("gate", password="x")
        UserProfile.objects.create(user=self.guard, role="GUARD", approval_status="APPROVED")
        self.url = reverse("notifications:list")

    def approve_person(self):
        req, _, err = services.submit("person", self.resident, {
            "first_name": "Ramon", "last_name": "Villanueva", "reason": "Trespassing"}, consent=True)
        self.assertIsNone(err)
        return req, services.approve_request("person", req.pk, self.admin)

    def test_login_required(self):
        self.assertIn(reverse("login:login"), self.client.get(self.url)["Location"])

    def test_feed_shows_only_my_notifications_newest_first(self):
        self.approve_person()
        Notification.objects.create(recipient=self.other, title="Not yours", message="x",
                                    notification_type="REQUEST_STATUS")
        self.client.force_login(self.resident)
        page = self.client.get(self.url)
        self.assertEqual([x["obj"].title for x in page.context["items"]], ["Restriction request approved"])
        self.assertNotContains(page, "Not yours")
        self.assertEqual(page.context["counts"], {"all": 1, "unread": 1})

    def test_bell_shows_unread_count_for_every_role(self):
        self.approve_person()  # resident: approved; guard: new restriction
        for user, expected in ((self.resident, 1), (self.guard, 1), (self.admin, 0)):
            self.client.force_login(user)
            page = self.client.get(reverse("profile:profile"))
            self.assertEqual(page.context["shell_unread"], expected, user.username)
            self.assertContains(page, reverse("notifications:list"))
        self.client.force_login(self.resident)
        self.assertContains(self.client.get(reverse("profile:profile")), '<span class="bell-n">1</span>', html=False)

    def test_opening_marks_read_and_goes_to_the_right_page(self):
        req, restricted = self.approve_person()
        gate.record_match(self.guard, "person", restricted.pk, "ramon", "MAIN_GATE", "ESCALATED_TO_ADMIN")
        cases = [
            (self.resident, "Restriction request approved", reverse("restrictions:mine")),
            (self.resident, "Gate check: Ramon Villanueva", reverse("restrictions:mine")),
            (self.guard, "New restricted person", reverse("guard:search")),
            (self.admin, "Gate escalation: Ramon Villanueva", reverse("guard:log")),
        ]
        for user, title, url in cases:
            note = Notification.objects.get(recipient=user, title=title)
            self.client.force_login(user)
            self.assertRedirects(self.client.get(reverse("notifications:open", args=[note.pk])), url,
                                 fetch_redirect_response=False)
            note.refresh_from_db()
            self.assertTrue(note.is_read, title)

    def test_admin_request_and_account_targets(self):
        from apps.notifications.views import target_url

        req, _ = self.approve_person()
        note = Notification(target_entity="PersonRestrictionRequest", target_id=req.pk)
        self.assertEqual(target_url(note, self.admin), reverse("restrictions:review", args=["person", req.pk]))
        account = Notification(target_entity="UserProfile", target_id=1)
        self.assertEqual(target_url(account, self.resident), reverse("home:home"))
        self.assertEqual(target_url(Notification(target_entity=""), self.resident), self.url)

    def test_cannot_open_someone_elses_notification(self):
        self.approve_person()
        note = Notification.objects.get(recipient=self.resident)
        self.client.force_login(self.other)
        self.assertEqual(self.client.get(reverse("notifications:open", args=[note.pk])).status_code, 404)
        note.refresh_from_db()
        self.assertFalse(note.is_read)

    def test_unread_tab_and_mark_all_read(self):
        self.approve_person()
        Notification.objects.create(recipient=self.resident, title="Older", message="x",
                                    notification_type="REQUEST_STATUS", is_read=True)
        Notification.objects.create(recipient=self.other, title="Other", message="x", notification_type="REQUEST_STATUS")
        self.client.force_login(self.resident)
        self.assertEqual(len(self.client.get(self.url, {"show": "unread"}).context["items"]), 1)
        self.assertEqual(self.client.get(reverse("notifications:read_all")).status_code, 405)
        resp = self.client.post(reverse("notifications:read_all"))
        self.assertRedirects(resp, self.url, fetch_redirect_response=False)
        self.assertFalse(Notification.objects.filter(recipient=self.resident, is_read=False).exists())
        self.assertTrue(Notification.objects.filter(recipient=self.other, is_read=False).exists())
        page = self.client.get(self.url, {"show": "unread"})
        self.assertContains(page, "all caught up")
        self.assertNotContains(page, "Mark all as read")
