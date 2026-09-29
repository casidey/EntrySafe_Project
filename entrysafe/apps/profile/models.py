from django.contrib.auth.models import User
from django.db import models, transaction
from django.utils import timezone


class ReviewError(Exception):
    """Raised when an account cannot be reviewed (already decided, etc.)."""


class UserProfile(models.Model):
    """ERD entity USER_PROFILE. 1-to-1 with AUTH_USER.

    It also carries the registration approval state: a new resident starts as PENDING
    (their AUTH_USER is inactive) until an admin approves or disapproves the account.
    """

    class Role(models.TextChoices):
        RESIDENT = "RESIDENT", "Resident"
        ADMIN = "ADMIN", "Admin"
        GUARD = "GUARD", "Guard"

    class ApprovalStatus(models.TextChoices):
        PENDING = "PENDING", "Pending"
        APPROVED = "APPROVED", "Approved"
        DISAPPROVED = "DISAPPROVED", "Disapproved"

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="profile")
    role = models.CharField(max_length=20, choices=Role.choices, default=Role.RESIDENT)
    full_name = models.CharField(max_length=150, blank=True)  # legal full name
    unit_number = models.CharField(max_length=60, blank=True)  # condominium tower and unit number
    contact_number = models.CharField(max_length=40, blank=True)  # mobile phone number
    id_proof_image = models.FileField(upload_to="id_proofs/%Y/%m/", blank=True)  # resident ID / proof of residency
    approval_status = models.CharField(
        max_length=20, choices=ApprovalStatus.choices, default=ApprovalStatus.PENDING
    )
    reviewed_by = models.ForeignKey(
        User, null=True, blank=True, on_delete=models.SET_NULL, related_name="reviewed_profiles"
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    disapproval_reason = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)  # registration submission timestamp
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "user_profile"

    def __str__(self):
        return f"{self.user.username} ({self.role})"

    # ---- helpers used by the UI
    @classmethod
    def for_user(cls, user):
        """Profile for a user, creating an already-approved one for accounts made outside
        the registration form (e.g. createsuperuser)."""
        profile, _ = cls.objects.get_or_create(
            user=user,
            defaults={
                "role": cls.Role.ADMIN if user.is_staff else cls.Role.RESIDENT,
                "approval_status": cls.ApprovalStatus.APPROVED,
                "full_name": user.get_full_name(),
            },
        )
        return profile

    @property
    def unit_label(self):
        return self.unit_number

    @property
    def reference(self):
        return f"ES-{self.pk:04d}"

    @property
    def is_pending(self):
        return self.approval_status == self.ApprovalStatus.PENDING

    # ---- admin decisions
    def _decide(self, admin_user, status, reason=""):
        with transaction.atomic():
            p = UserProfile.objects.select_for_update().select_related("user").get(pk=self.pk)
            if p.approval_status != self.ApprovalStatus.PENDING:
                raise ReviewError("This registration has already been reviewed.")
            p.approval_status = status
            p.reviewed_by = admin_user
            p.reviewed_at = timezone.now()
            p.disapproval_reason = reason
            p.user.is_active = status == self.ApprovalStatus.APPROVED
            p.user.save(update_fields=["is_active"])
            p.save()
            self.__dict__.update({k: v for k, v in p.__dict__.items() if k != "_state"})
        return p

    def approve(self, admin_user, request=None):
        from apps.audit.models import AuditLog
        from apps.notifications.models import Notification

        p = self._decide(admin_user, self.ApprovalStatus.APPROVED)
        AuditLog.record(admin_user, AuditLog.Action.APPROVE_ACCOUNT, "UserProfile", p.pk,
                        f"Approved account of {p.full_name or p.user.username}.", request)
        Notification.objects.create(
            recipient=p.user, title="Account approved",
            message="The administrator approved your registration. You can now use EntrySafe.",
            notification_type=Notification.Type.ACCOUNT_STATUS, target_entity="UserProfile", target_id=p.pk)
        return p.user

    def disapprove(self, admin_user, reason="", request=None):
        from apps.audit.models import AuditLog
        from apps.notifications.models import Notification

        p = self._decide(admin_user, self.ApprovalStatus.DISAPPROVED, reason.strip())
        AuditLog.record(admin_user, AuditLog.Action.DISAPPROVE_ACCOUNT, "UserProfile", p.pk,
                        f"Disapproved account of {p.full_name or p.user.username}."
                        + (f" Reason: {p.disapproval_reason}" if p.disapproval_reason else ""), request)
        Notification.objects.create(
            recipient=p.user, title="Account not approved",
            message=p.disapproval_reason or "The administrator did not approve your registration.",
            notification_type=Notification.Type.ACCOUNT_STATUS, target_entity="UserProfile", target_id=p.pk)
