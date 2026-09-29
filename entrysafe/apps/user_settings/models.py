from django.contrib.auth.models import User
from django.db import models


class UserSettings(models.Model):
    """ERD entity USER_SETTINGS (1-to-1 with AUTH_USER)."""

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="settings")
    dark_mode = models.BooleanField(default=False)  # UI theme preference
    email_notifications = models.BooleanField(default=True)  # email alert preference
    updated_at = models.DateTimeField(auto_now=True)  # last settings update

    class Meta:
        db_table = "user_settings"
        verbose_name_plural = "user settings"

    def __str__(self):
        return f"Settings for {self.user.username}"
