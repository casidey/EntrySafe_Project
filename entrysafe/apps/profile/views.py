from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST

from apps.audit.models import AuditLog

from . import services
from .models import ResidentVehicle, UserProfile

ROLE_LABELS = {"ADMIN": "Administrator", "GUARD": "Guard", "RESIDENT": "Resident"}


def _context(request, **extra):
    user = request.user
    profile = UserProfile.for_user(user)
    role = "ADMIN" if user.is_staff else profile.role
    reviewer = profile.reviewed_by
    ctx = {
        "profile": profile,
        "role_label": ROLE_LABELS.get(role, role.title()),
        "is_resident": services.is_resident(user),
        "reviewer_name": ((getattr(getattr(reviewer, "profile", None), "full_name", "") or reviewer.get_username())
                          if reviewer else ""),
        "form": {k: getattr(profile, k) for k in services.DETAIL_FIELDS},
        "vehicles": ResidentVehicle.objects.filter(resident=user),
        "vehicle_types": ResidentVehicle.VEHICLE_TYPES,
        "vehicle_form": {"vehicle_type": "SEDAN"},
        "max_vehicles": ResidentVehicle.MAX_PER_RESIDENT,
        "activity": AuditLog.objects.filter(user=user)[:5],
    }
    ctx.update(extra)
    return ctx


@login_required(login_url="login:login")
def profile_view(request):
    if request.method == "POST":
        form, error = services.update_details(request.user, request.POST, request=request)
        if error is None:
            messages.success(request, "Profile saved.")
            return redirect("profile:profile")
        return render(request, "profile/profile.html", _context(request, form=form, error=error))
    return render(request, "profile/profile.html", _context(request))


@login_required(login_url="login:login")
@require_POST
def password_view(request):
    form = services.change_password(request, request.POST)
    if form.is_valid():
        messages.success(request, "Password changed. You stay signed in here; other devices are signed out.")
        return redirect("profile:profile")
    errors = [e for errs in form.errors.values() for e in errs]
    return render(request, "profile/profile.html", _context(request, password_errors=errors))


@login_required(login_url="login:login")
@require_POST
def vehicle_add_view(request):
    try:
        vehicle, form, error = services.add_vehicle(request.user, request.POST, request=request)
    except services.ProfileError as exc:
        messages.error(request, str(exc))
        return redirect("profile:profile")
    if error is None:
        messages.success(request, f"Added {vehicle.license_plate}.")
        return redirect("profile:profile")
    return render(request, "profile/profile.html", _context(request, vehicle_form=form, vehicle_error=error))


@login_required(login_url="login:login")
@require_POST
def vehicle_remove_view(request, pk):
    try:
        vehicle = services.remove_vehicle(request.user, pk, request=request)
    except services.ProfileError as exc:
        messages.error(request, str(exc))
    else:
        messages.success(request, f"Removed {vehicle.license_plate}.")
    return redirect("profile:profile")
