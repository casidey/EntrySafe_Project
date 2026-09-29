from django.contrib.auth.models import User
from django.db import models


class Notification(models.Model):
    """ERD entity NOTIFICATION: an alert for one user (AUTH_USER 'receives')."""

    class Type(models.TextChoices):
        ACCOUNT_STATUS = "ACCOUNT_STATUS", "Account status"
        REQUEST_STATUS = "REQUEST_STATUS", "Request status"
        NEW_RESTRICTION = "NEW_RESTRICTION", "New restriction"

    recipient = models.ForeignKey(User, on_delete=models.CASCADE, related_name="notifications")
    title = models.CharField(max_length=150)  # alert subject title
    message = models.TextField()  # notification body text
    notification_type = models.CharField(max_length=30, choices=Type.choices)
    target_entity = models.CharField(max_length=60, blank=True)  # target model name, e.g. UserProfile
    target_id = models.IntegerField(null=True, blank=True)  # primary key of the target record
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "notification"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.title} -> {self.recipient.username}"
