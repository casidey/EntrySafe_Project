"""Restriction request workflow (Phase 3).

Everything that changes state lives here so the views stay thin and each action
writes its AuditLog row and Notification in one place:

    resident submits  -> PENDING request
    resident cancels  -> CANCELLED (only while PENDING)
    admin approves    -> APPROVED + a RestrictedPerson / RestrictedVehicle (ACTIVE)
    admin rejects     -> REJECTED
    resident or admin removes a restriction -> REVOKED
    end_date passes   -> EXPIRED (checked whenever a list is read)
"""
import os
from datetime import date

from django.contrib.auth.models import User
from django.core.files.base import ContentFile
from django.db import transaction
from django.utils import timezone

from apps.audit.models import AuditLog
from apps.notifications.models import Notification
from apps.profile.models import UserProfile

from .models import (
    VEHICLE_TYPES, PersonRestrictionRequest, RequestStatus, RestrictedPerson, RestrictedVehicle,
    RestrictionStatus, VehicleRestrictionRequest)

PERSON, VEHICLE = "person", "vehicle"
KINDS = (PERSON, VEHICLE)
REQUEST_MODELS = {PERSON: PersonRestrictionRequest, VEHICLE: VehicleRestrictionRequest}
RESTRICTED_MODELS = {PERSON: RestrictedPerson, VEHICLE: RestrictedVehicle}

ALLOWED_PHOTO_EXT = {".png", ".jpg", ".jpeg"}
MAX_PHOTO_BYTES = 5 * 1024 * 1024


class RestrictionError(Exception):
    """An action that is not allowed (wrong status, not the owner, bad input)."""


# ---------------------------------------------------------------- who is who
def is_resident(user):
    """An approved, active, non-staff resident: the only role that files requests."""
    if not user.is_authenticated or not user.is_active or user.is_staff:
        return False
    profile = getattr(user, "profile", None)
    if profile is None:  # account made outside the registration form
        return True
    return (profile.role == UserProfile.Role.RESIDENT
            and profile.approval_status == UserProfile.ApprovalStatus.APPROVED)


def _admins():
    return User.objects.filter(is_staff=True, is_active=True)


def _guards():
    return User.objects.filter(is_active=True, is_staff=False, profile__role=UserProfile.Role.GUARD)


def _notify(users, title, message, ntype, entity, pk):
    Notification.objects.bulk_create([
        Notification(recipient=u, title=title, message=message, notification_type=ntype,
                     target_entity=entity, target_id=pk)
        for u in users
    ])


# ---------------------------------------------------------------- labels
def label(kind, obj):
    """Short human name for a request or a restriction, e.g. 'Juan Cruz' or 'NBX 4471'."""
    if kind == PERSON:
        return f"{obj.first_name} {obj.last_name}".strip()
    return obj.license_plate


def normalise_plate(value):
    return " ".join(value.upper().split())


# ---------------------------------------------------------------- validation
def _clean_photo(photo):
    if not photo:
        return None
    if os.path.splitext(photo.name)[1].lower() not in ALLOWED_PHOTO_EXT:
        raise RestrictionError("The photo must be a PNG or JPG image.")
    if photo.size > MAX_PHOTO_BYTES:
        raise RestrictionError("The photo is larger than 5MB.")
    try:
        from PIL import Image

        Image.open(photo).verify()
    except Exception:
        raise RestrictionError("The photo could not be read. Please upload a PNG or JPG image.")
    photo.seek(0)
    return photo


def clean_person(data):
    form = {k: data.get(k, "").strip() for k in
            ("first_name", "last_name", "alias_nickname", "relationship_to_resident", "reason")}
    if not form["first_name"] or not form["last_name"]:
        return form, "Please enter the person's first and last name."
    if not form["reason"]:
        return form, "Please explain why this person should be restricted."
    for k, limit in (("first_name", 80), ("last_name", 80), ("alias_nickname", 80), ("relationship_to_resident", 80)):
        if len(form[k]) > limit:
            return form, "One of the fields is too long (80 characters at most)."
    return form, None


def clean_vehicle(data):
    form = {k: data.get(k, "").strip() for k in ("license_plate", "vehicle_type", "make_model", "color", "reason")}
    form["license_plate"] = normalise_plate(form["license_plate"])
    if not form["license_plate"]:
        return form, "Please enter the vehicle's plate number."
    if len(form["license_plate"]) > 20:
        return form, "The plate number is too long (20 characters at most)."
    if form["vehicle_type"] not in dict(VEHICLE_TYPES):
        return form, "Please choose the vehicle type."
    if len(form["make_model"]) > 100 or len(form["color"]) > 40:
        return form, "The make/model or color is too long."
    if not form["reason"]:
        return form, "Please explain why this vehicle should be restricted."
    return form, None


# ---------------------------------------------------------------- resident actions
def submit(kind, resident, data, photo=None, consent=False, request=None):
    """Validate and create a PENDING request. Returns (obj, form, error)."""
    form, error = (clean_person if kind == PERSON else clean_vehicle)(data)
    if error is None and not is_resident(resident):
        error = "Only approved residents can submit restriction requests."
    if error is None:
        try:
            photo = _clean_photo(photo)
        except RestrictionError as exc:
            error = str(exc)
    if error is None and not consent:
        error = "Please confirm you have the right to submit this information."
    if error:
        return None, form, error

    model = REQUEST_MODELS[kind]
    with transaction.atomic():
        obj = model(resident=resident, **form)
        if photo:
            obj.photo = photo
        obj.save()
        AuditLog.record(resident, AuditLog.Action.SUBMIT_REQUEST, model.__name__, obj.pk,
                        f"Submitted a {kind} restriction request for {label(kind, obj)}.", request)
    return obj, form, None


def cancel_request(kind, pk, resident, request=None):
    model = REQUEST_MODELS[kind]
    with transaction.atomic():
        obj = model.objects.select_for_update().filter(pk=pk, resident=resident).first()
        if obj is None:
            raise RestrictionError("That request was not found.")
        if obj.status != RequestStatus.PENDING:
            raise RestrictionError("Only a pending request can be cancelled.")
        obj.status = RequestStatus.CANCELLED
        obj.save(update_fields=["status", "updated_at"])
        AuditLog.record(resident, AuditLog.Action.CANCEL_REQUEST, model.__name__, obj.pk,
                        f"Cancelled the {kind} restriction request for {label(kind, obj)}.", request)
    return obj


# ---------------------------------------------------------------- admin review
def _copy_photo(source, target):
    """Give the restriction its own copy of the request photo (missing files are skipped)."""
    if not source.photo:
        return
    try:
        with source.photo.open("rb") as fh:
            target.photo.save(os.path.basename(source.photo.name), ContentFile(fh.read()), save=False)
    except (FileNotFoundError, OSError):
        pass


def parse_end_date(value):
    """'' -> None (permanent); 'YYYY-MM-DD' -> date, which must not be in the past."""
    value = (value or "").strip()
    if not value:
        return None
    try:
        end = date.fromisoformat(value)
    except ValueError:
        raise RestrictionError("Please enter a valid end date.")
    if end < timezone.localdate():
        raise RestrictionError("The end date cannot be in the past.")
    return end


def _lock_pending(kind, pk):
    obj = REQUEST_MODELS[kind].objects.select_for_update(of=("self",)).select_related("resident").filter(pk=pk).first()
    if obj is None:
        raise RestrictionError("That request was not found.")
    if obj.status != RequestStatus.PENDING:
        raise RestrictionError("This request has already been reviewed or cancelled.")
    return obj


def approve_request(kind, pk, admin, remarks="", guard_instructions="", end_date="", request=None):
    """Approve a pending request and create the matching ACTIVE restriction."""
    end = parse_end_date(end_date) if not isinstance(end_date, date) else end_date
    with transaction.atomic():
        req = _lock_pending(kind, pk)
        req.status = RequestStatus.APPROVED
        req.reviewed_by = admin
        req.reviewed_at = timezone.now()
        req.admin_remarks = remarks.strip()
        req.save()

        common = dict(request=req, approved_by=admin, restriction_reason=req.reason,
                      guard_instructions=guard_instructions.strip(), start_date=timezone.localdate(), end_date=end)
        if kind == PERSON:
            restricted = RestrictedPerson(first_name=req.first_name, last_name=req.last_name,
                                          alias_nickname=req.alias_nickname, **common)
        else:
            restricted = RestrictedVehicle(license_plate=req.license_plate, vehicle_type=req.vehicle_type,
                                           make_model=req.make_model, color=req.color, **common)
        _copy_photo(req, restricted)
        restricted.save()

        name = label(kind, req)
        until = f" until {end:%b %d, %Y}" if end else ""
        AuditLog.record(admin, AuditLog.Action.APPROVE_REQUEST, type(req).__name__, req.pk,
                        f"Approved the {kind} restriction request for {name}{until}.", request)
        _notify([req.resident], "Restriction request approved",
                f"Your request to restrict {name} was approved{until}."
                + (f" Remarks: {req.admin_remarks}" if req.admin_remarks else ""),
                Notification.Type.REQUEST_STATUS, type(req).__name__, req.pk)
        _notify(_guards(), f"New restricted {kind}",
                f"{name} is now on the restricted list{until}."
                + (f" Instructions: {restricted.guard_instructions}" if restricted.guard_instructions else ""),
                Notification.Type.NEW_RESTRICTION, type(restricted).__name__, restricted.pk)
    return restricted


def reject_request(kind, pk, admin, remarks="", request=None):
    with transaction.atomic():
        req = _lock_pending(kind, pk)
        req.status = RequestStatus.REJECTED
        req.reviewed_by = admin
        req.reviewed_at = timezone.now()
        req.admin_remarks = remarks.strip()
        req.save()
        name = label(kind, req)
        AuditLog.record(admin, AuditLog.Action.REJECT_REQUEST, type(req).__name__, req.pk,
                        f"Rejected the {kind} restriction request for {name}."
                        + (f" Remarks: {req.admin_remarks}" if req.admin_remarks else ""), request)
        _notify([req.resident], "Restriction request rejected",
                req.admin_remarks or f"The administrator did not approve your request to restrict {name}.",
                Notification.Type.REQUEST_STATUS, type(req).__name__, req.pk)
    return req


# ---------------------------------------------------------------- removal & expiry
def revoke_restriction(kind, pk, actor, request=None):
    """End an ACTIVE restriction. Allowed for an admin, or the resident who filed it
    (self-service: no admin approval needed to lift a restriction)."""
    model = RESTRICTED_MODELS[kind]
    with transaction.atomic():
        obj = model.objects.select_for_update(of=("self",)).select_related("request__resident").filter(pk=pk).first()
        owner = obj.request.resident if obj is not None and obj.request_id else None
        if obj is None or not (actor.is_staff or (owner is not None and owner == actor and is_resident(actor))):
            raise RestrictionError("That restriction was not found.")
        if obj.status != RestrictionStatus.ACTIVE:
            raise RestrictionError("This restriction is no longer active.")
        obj.status = RestrictionStatus.REVOKED
        obj.save(update_fields=["status", "updated_at"])

        name = label(kind, obj)
        by = "the administrator" if actor.is_staff else "the resident who requested it"
        AuditLog.record(actor, AuditLog.Action.REVOKE_RESTRICTION, model.__name__, obj.pk,
                        f"Removed the restriction on {name} (by {by}).", request)
        if actor.is_staff:
            recipients = [owner] if owner is not None else []
        else:
            recipients = list(_admins())
        _notify(list(recipients) + list(_guards()), "Restriction removed",
                f"The restriction on {name} was removed by {by}.",
                Notification.Type.REQUEST_STATUS, model.__name__, obj.pk)
    return obj


def expire_due():
    """Checked-on-read expiry: ACTIVE restrictions whose end_date has passed become EXPIRED.
    A restriction is still in force on its end_date itself."""
    today = timezone.localdate()
    changed = 0
    for model in RESTRICTED_MODELS.values():
        changed += model.objects.filter(status=RestrictionStatus.ACTIVE, end_date__lt=today).update(
            status=RestrictionStatus.EXPIRED, updated_at=timezone.now())
    return changed


# ---------------------------------------------------------------- counts for dashboards
def pending_request_count(resident=None):
    total = 0
    for model in REQUEST_MODELS.values():
        qs = model.objects.filter(status=RequestStatus.PENDING)
        total += (qs.filter(resident=resident) if resident is not None else qs).count()
    return total


def active_restriction_count(resident=None):
    expire_due()
    total = 0
    for model in RESTRICTED_MODELS.values():
        qs = model.objects.filter(status=RestrictionStatus.ACTIVE)
        total += (qs.filter(request__resident=resident) if resident is not None else qs).count()
    return total
