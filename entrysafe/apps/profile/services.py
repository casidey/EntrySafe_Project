"""Profile changes a signed-in user makes to their own account (each one is audited)."""
import re

from django.contrib.auth import update_session_auth_hash
from django.contrib.auth.forms import PasswordChangeForm
from django.db import transaction
from django.db.models import Value
from django.db.models.functions import Replace, Upper

from apps.audit.models import AuditLog

from .models import ResidentVehicle, UserProfile

PLATE_RE = re.compile(r"^[A-Z0-9][A-Z0-9 -]{1,18}[A-Z0-9]$")


class ProfileError(Exception):
    """The change was refused; the message is shown to the user."""


def plate_key(value):
    """'nbx-4471', 'NBX 4471' and 'nbx4471' all become 'NBX4471'."""
    return re.sub(r"[^A-Z0-9]", "", (value or "").upper())


def is_resident(user):
    profile = getattr(user, "profile", None)
    return (not user.is_staff and profile is not None and profile.role == UserProfile.Role.RESIDENT
            and profile.approval_status == UserProfile.ApprovalStatus.APPROVED)


# ---------------------------------------------------------------- details
DETAIL_FIELDS = {
    "full_name": ("full name", 150),
    "contact_number": ("contact number", 40),
    "emergency_contact_name": ("emergency contact name", 150),
    "emergency_contact_relationship": ("emergency contact relationship", 60),
    "emergency_contact_number": ("emergency contact number", 40),
}


def update_details(user, data, request=None):
    """Save the user's own name, contact number and emergency contact. Returns (form, error)."""
    profile = UserProfile.for_user(user)
    form = {k: " ".join((data.get(k) or "").split()) for k in DETAIL_FIELDS}
    if not form["full_name"]:
        return form, "Please enter your full name."
    for key, (label, limit) in DETAIL_FIELDS.items():
        if len(form[key]) > limit:
            return form, f"Your {label} is too long ({limit} characters at most)."
    for key in ("contact_number", "emergency_contact_number"):
        if form[key] and not re.fullmatch(r"[0-9+()\- ]{7,40}", form[key]):
            return form, "Phone numbers may contain only digits, spaces and + ( ) -."
    emergency = [form["emergency_contact_name"], form["emergency_contact_number"]]
    if any(emergency) and not all(emergency):
        return form, "Please give both a name and a number for your emergency contact."

    changed = [DETAIL_FIELDS[k][0] for k in DETAIL_FIELDS if (getattr(profile, k) or "") != form[k]]
    if not changed:
        return form, None
    with transaction.atomic():
        for key in DETAIL_FIELDS:
            setattr(profile, key, form[key])
        profile.save()
        if user.first_name != form["full_name"]:
            user.first_name = form["full_name"][:150]
            user.save(update_fields=["first_name"])
        AuditLog.record(user, AuditLog.Action.UPDATE_PROFILE, "UserProfile", profile.pk,
                        f"Updated own profile: {', '.join(changed)}.", request)
    return form, None


# ---------------------------------------------------------------- password
def change_password(request, data):
    """Change the signed-in user's password. Returns the bound form (check form.is_valid() / errors)."""
    form = PasswordChangeForm(request.user, data)
    if form.is_valid():
        with transaction.atomic():
            user = form.save()
            update_session_auth_hash(request, user)  # keep this session; other sessions are signed out
            AuditLog.record(user, AuditLog.Action.CHANGE_PASSWORD, "UserProfile", UserProfile.for_user(user).pk,
                            "Changed own password.", request)
    return form


# ---------------------------------------------------------------- resident vehicles
def add_vehicle(user, data, request=None):
    """Register one of the resident's own vehicles. Returns (vehicle, form, error)."""
    form = {k: " ".join((data.get(k) or "").split()) for k in ("license_plate", "vehicle_type", "make_model", "color")}
    form["license_plate"] = form["license_plate"].upper()
    if not is_resident(user):
        raise ProfileError("Only residents can register vehicles.")
    if not PLATE_RE.fullmatch(form["license_plate"]):
        return None, form, "Enter a plate number using letters, numbers, spaces or dashes (3 to 20 characters)."
    if form["vehicle_type"] not in dict(ResidentVehicle.VEHICLE_TYPES):
        return None, form, "Please choose the vehicle type."
    if len(form["make_model"]) > 100 or len(form["color"]) > 40:
        return None, form, "Make/model or color is too long."
    mine = ResidentVehicle.objects.filter(resident=user)
    if mine.count() >= ResidentVehicle.MAX_PER_RESIDENT:
        return None, form, f"You can register up to {ResidentVehicle.MAX_PER_RESIDENT} vehicles."
    if any(plate_key(v.license_plate) == plate_key(form["license_plate"]) for v in mine):
        return None, form, "You already registered this plate."
    with transaction.atomic():
        vehicle = ResidentVehicle.objects.create(resident=user, **form)
        AuditLog.record(user, AuditLog.Action.ADD_VEHICLE, "ResidentVehicle", vehicle.pk,
                        f"Registered own vehicle {vehicle.license_plate}.", request)
    return vehicle, form, None


def remove_vehicle(user, pk, request=None):
    vehicle = ResidentVehicle.objects.filter(pk=pk, resident=user).first()
    if vehicle is None:
        raise ProfileError("That vehicle was not found.")
    with transaction.atomic():
        AuditLog.record(user, AuditLog.Action.REMOVE_VEHICLE, "ResidentVehicle", vehicle.pk,
                        f"Removed own vehicle {vehicle.license_plate}.", request)
        vehicle.delete()
    return vehicle


def resident_vehicles_matching(query):
    """Vehicles of ACTIVE residents whose plate contains the searched plate (for Gate check)."""
    key = plate_key(query)
    if len(key) < 3:
        return ResidentVehicle.objects.none()
    plate = Replace(Replace(Upper("license_plate"), Value(" "), Value("")), Value("-"), Value(""))
    return (ResidentVehicle.objects.filter(resident__is_active=True).select_related("resident__profile")
            .annotate(plate_key=plate).filter(plate_key__contains=key))
