"""Account management (Phase 5): administrators edit and deactivate/reactivate accounts.

Covers guards, administrators and approved residents (a resident who moves out is deactivated,
not deleted, so their history stays). Pending or disapproved registrations are handled on the
Registrations page instead.

A deactivated account is an inactive auth User whose profile is still APPROVED, so it can be told
apart from a registration that is waiting for approval (also inactive, but PENDING).
"""
from django.contrib.auth.models import User
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.db import transaction

from apps.audit.models import AuditLog
from apps.notifications.models import Notification
from apps.profile.models import UserProfile

ROLE_LABELS = {"ADMIN": "Administrator", "GUARD": "Guard", "RESIDENT": "Resident"}


class AccountError(Exception):
    """The change was refused (would lock everyone out, not allowed for this account, etc.)."""


def role_of(user):
    """ADMIN / GUARD / RESIDENT for an account an admin may manage here, else None."""
    if user.is_staff:
        return "ADMIN"
    profile = getattr(user, "profile", None)
    if profile is None:
        return None
    if profile.role == UserProfile.Role.GUARD:
        return "GUARD"
    if profile.role == UserProfile.Role.RESIDENT and profile.approval_status == UserProfile.ApprovalStatus.APPROVED:
        return "RESIDENT"
    return None


def display_name(user):
    profile = getattr(user, "profile", None)
    return (profile.full_name if profile and profile.full_name else user.get_full_name()) or user.username


def _notify(user, title, message):
    Notification.objects.create(recipient=user, title=title, message=message,
                                notification_type=Notification.Type.ACCOUNT_STATUS,
                                target_entity="UserProfile", target_id=user.profile.pk)


def _active_admins_other_than(user):
    return User.objects.filter(is_staff=True, is_active=True).exclude(pk=user.pk).count()


def update_account(admin, user, data, request=None):
    """Save name, email, contact (and unit for residents), optionally set a new password.
    Returns (form, error); error is None on success."""
    role = role_of(user)
    if role is None:
        raise AccountError("This account is managed on the Registrations page.")
    profile = UserProfile.for_user(user)
    form = {k: (data.get(k) or "").strip() for k in ("full_name", "email", "contact_number", "unit_number")}
    password = data.get("new_password", "")
    if not form["full_name"]:
        return form, "Please enter a full name."
    if len(form["full_name"]) > 150 or len(form["contact_number"]) > 40 or len(form["unit_number"]) > 60:
        return form, "One of the fields is too long."
    if role == "RESIDENT" and not form["unit_number"]:
        return form, "Please enter the resident's tower and unit."
    if form["email"]:
        try:
            validate_email(form["email"])
        except ValidationError:
            return form, "Please enter a valid email address."
        if User.objects.filter(email__iexact=form["email"]).exclude(pk=user.pk).exists():
            return form, "Another account already uses this email."
    if password:
        try:
            validate_password(password, user)
        except ValidationError as exc:
            return form, " ".join(exc.messages)

    changed = [label for label, old, new in (
        ("name", profile.full_name, form["full_name"]),
        ("email", user.email, form["email"]),
        ("contact number", profile.contact_number, form["contact_number"]),
        ("unit", profile.unit_number, form["unit_number"] if role == "RESIDENT" else profile.unit_number),
    ) if (old or "") != new]
    if password:
        changed.append("password")
    if not changed:
        return form, None

    with transaction.atomic():
        profile.full_name, profile.contact_number = form["full_name"], form["contact_number"]
        if role == "RESIDENT":
            profile.unit_number = form["unit_number"]
        profile.save()
        user.email, user.first_name = form["email"], form["full_name"]
        if password:
            user.set_password(password)  # also signs them out of other sessions
        user.save()
        AuditLog.record(admin, AuditLog.Action.UPDATE_ACCOUNT, "UserProfile", profile.pk,
                        f"Updated {ROLE_LABELS[role].lower()} account {user.username}: {', '.join(changed)}.", request)
        if user != admin:
            _notify(user, "Account details updated",
                    f"An administrator updated your {', '.join(changed)}."
                    + (" Use the new password the administrator gave you." if password else ""))
    return form, None


def set_active(admin, user, active, reason="", request=None):
    """Deactivate (active=False) or reactivate an account. Raises AccountError if not allowed."""
    role = role_of(user)
    if role is None:
        raise AccountError("This account is managed on the Registrations page.")
    if user.is_active == active:
        raise AccountError("This account is already " + ("active." if active else "deactivated."))
    if not active and user == admin:
        raise AccountError("You cannot deactivate your own account.")
    if not active and role == "ADMIN" and _active_admins_other_than(user) == 0:
        raise AccountError("At least one administrator must stay active.")
    reason = " ".join((reason or "").split())[:300]

    with transaction.atomic():
        user.is_active = active
        user.save(update_fields=["is_active"])
        label = f"{ROLE_LABELS[role].lower()} account {user.username}"
        if active:
            AuditLog.record(admin, AuditLog.Action.REACTIVATE_ACCOUNT, "UserProfile", user.profile.pk,
                            f"Reactivated {label}.", request)
            _notify(user, "Account reactivated", "An administrator reactivated your account. You can sign in again.")
        else:
            AuditLog.record(admin, AuditLog.Action.DEACTIVATE_ACCOUNT, "UserProfile", user.profile.pk,
                            f"Deactivated {label}." + (f" Reason: {reason.rstrip('.')}." if reason else ""), request)
    return user
