from django.contrib.auth.models import User
from django.db import models


class AuditLog(models.Model):
    """ERD entity AUDIT_LOG: a record of a state-changing action ('performed_by' AUTH_USER)."""

    class Action(models.TextChoices):
        APPROVE_ACCOUNT = "APPROVE_ACCOUNT", "Approve account"
        DISAPPROVE_ACCOUNT = "DISAPPROVE_ACCOUNT", "Disapprove account"
        APPROVE_REQUEST = "APPROVE_REQUEST", "Approve request"
        REJECT_REQUEST = "REJECT_REQUEST", "Reject request"
        REVOKE_RESTRICTION = "REVOKE_RESTRICTION", "Revoke restriction"

    user = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name="audit_logs")
    action = models.CharField(max_length=30, choices=Action.choices)
    target_entity = models.CharField(max_length=60)  # affected table/model name
    target_id = models.IntegerField(null=True, blank=True)  # affected record primary key
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    change_summary = models.TextField(blank=True)
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "audit_log"
        ordering = ["-timestamp"]

    def __str__(self):
        return f"{self.action} {self.target_entity}#{self.target_id}"

    @classmethod
    def record(cls, user, action, target_entity, target_id, summary="", request=None):
        ip = None
        if request is not None:
            fwd = request.META.get("HTTP_X_FORWARDED_FOR", "")
            ip = (fwd.split(",")[0].strip() or request.META.get("REMOTE_ADDR")) or None
        return cls.objects.create(user=user, action=action, target_entity=target_entity,
                                  target_id=target_id, ip_address=ip, change_summary=summary)
