import mimetypes
from functools import wraps

from django.contrib import messages
from django.contrib.auth.decorators import login_required, user_passes_test
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from . import services
from .models import VEHICLE_TYPES, RequestStatus, RestrictionStatus
from .services import KINDS, PERSON, REQUEST_MODELS, RESTRICTED_MODELS, RestrictionError

staff_required = user_passes_test(lambda u: u.is_active and u.is_staff, login_url="login:login")


def _admin_only(view):
    return login_required(login_url="login:login")(staff_required(view))


def _resident_only(view):
    """Signed-in, approved residents only; everyone else goes back to their own home page."""
    @wraps(view)
    def wrapped(request, *args, **kwargs):
        if not services.is_resident(request.user):
            return redirect("home:home")
        return view(request, *args, **kwargs)
    return login_required(login_url="login:login")(wrapped)


def _kind(kind):
    if kind not in KINDS:
        raise Http404("Unknown restriction type.")
    return kind


# ---------------------------------------------------------------- rows for the templates
def _who(user):
    """(display name, unit) of the resident behind a request."""
    if user is None:
        return "", ""
    profile = getattr(user, "profile", None)
    return (profile.full_name if profile and profile.full_name else user.get_username(),
            profile.unit_number if profile else "")


def _request_row(kind, obj):
    if kind == PERSON:
        bits = [obj.alias_nickname and f'"{obj.alias_nickname}"', obj.relationship_to_resident]
    else:
        bits = [obj.get_vehicle_type_display(), obj.make_model, obj.color]
    return {
        "kind": kind, "obj": obj, "title": services.label(kind, obj),
        "detail": " · ".join(b for b in bits if b),
        "ref": f"{'PR' if kind == PERSON else 'VR'}-{obj.pk:04d}",
        "icon": "user" if kind == PERSON else "list",
        "type_label": "Person" if kind == PERSON else "Vehicle",
        "is_pending": obj.status == RequestStatus.PENDING,
        "resident_name": _who(obj.resident)[0], "resident_unit": _who(obj.resident)[1],
        "pill": {"APPROVED": "green", "REJECTED": "red", "CANCELLED": "red"}.get(obj.status, ""),
    }


def _restricted_row(kind, obj):
    if kind == PERSON:
        bits = [obj.alias_nickname and f'"{obj.alias_nickname}"']
    else:
        bits = [obj.get_vehicle_type_display(), obj.make_model, obj.color]
    return {
        "kind": kind, "obj": obj, "title": services.label(kind, obj),
        "detail": " · ".join(b for b in bits if b),
        "icon": "user" if kind == PERSON else "list",
        "type_label": "Person" if kind == PERSON else "Vehicle",
        "is_active": obj.status == RestrictionStatus.ACTIVE,
        "resident_name": _who(obj.request.resident if obj.request_id else None)[0],
        "resident_unit": _who(obj.request.resident if obj.request_id else None)[1],
        "pill": "green" if obj.status == RestrictionStatus.ACTIVE else "red",
    }


def _merged(models, row, **filters):
    rows = []
    for kind, model in models.items():
        related = ("resident__profile", "reviewed_by") if models is REQUEST_MODELS else ("request__resident__profile", "approved_by")
        rows += [row(kind, o) for o in model.objects.filter(**filters).select_related(*related)]
    rows.sort(key=lambda r: r["obj"].created_at, reverse=True)
    return rows


# ---------------------------------------------------------------- resident
@_resident_only
def my_requests_view(request):
    services.expire_due()
    ctx = {
        "requests": _merged(REQUEST_MODELS, _request_row, resident=request.user),
        "restrictions": _merged(RESTRICTED_MODELS, _restricted_row, request__resident=request.user,
                                status=RestrictionStatus.ACTIVE),
    }
    return render(request, "restrictions/my_requests.html", ctx)


@_resident_only
def new_request_view(request, kind):
    kind = _kind(kind)
    ctx = {"kind": kind, "vehicle_types": VEHICLE_TYPES, "form": {}}
    if request.method == "POST":
        obj, form, error = services.submit(
            kind, request.user, request.POST, photo=request.FILES.get("photo"),
            consent=request.POST.get("consent") == "on", request=request)
        if obj is not None:
            messages.success(request, f"Your request to restrict {services.label(kind, obj)} was sent for review.")
            return redirect("restrictions:mine")
        ctx.update(form=form, error=error)
    return render(request, "restrictions/request_form.html", ctx)


@_resident_only
@require_POST
def cancel_view(request, kind, pk):
    try:
        obj = services.cancel_request(_kind(kind), pk, request.user, request=request)
        messages.success(request, f"Your request to restrict {services.label(kind, obj)} was cancelled.")
    except RestrictionError as exc:
        messages.error(request, str(exc))
    return redirect("restrictions:mine")


@login_required(login_url="login:login")
@require_POST
def remove_view(request, kind, pk):
    """Residents remove their own restriction; admins can revoke any."""
    back = "restrictions:restricted" if request.user.is_staff else "restrictions:mine"
    if not (request.user.is_staff or services.is_resident(request.user)):
        return redirect("home:home")
    try:
        obj = services.revoke_restriction(_kind(kind), pk, request.user, request=request)
        messages.success(request, f"The restriction on {services.label(kind, obj)} was removed.")
    except RestrictionError as exc:
        messages.error(request, str(exc))
    return redirect(back)


# ---------------------------------------------------------------- photos (never served from MEDIA_URL)
def _serve(photo):
    if not photo:
        raise Http404("No photo on file.")
    try:
        fh = photo.open("rb")
    except (FileNotFoundError, OSError):
        raise Http404("Photo is missing from storage.")
    return FileResponse(fh, content_type=mimetypes.guess_type(photo.name)[0] or "application/octet-stream")


@login_required(login_url="login:login")
def request_photo_view(request, kind, pk):
    obj = get_object_or_404(REQUEST_MODELS[_kind(kind)], pk=pk)
    if not (request.user.is_staff or obj.resident_id == request.user.pk):
        raise Http404("No photo on file.")
    return _serve(obj.photo)


@login_required(login_url="login:login")
def restricted_photo_view(request, kind, pk):
    obj = get_object_or_404(RESTRICTED_MODELS[_kind(kind)].objects.select_related("request"), pk=pk)
    owner_id = obj.request.resident_id if obj.request_id else None
    if not (request.user.is_staff or owner_id == request.user.pk):
        raise Http404("No photo on file.")
    return _serve(obj.photo)


# ---------------------------------------------------------------- admin
QUEUE_TABS = {"pending": RequestStatus.PENDING, "approved": RequestStatus.APPROVED,
              "rejected": RequestStatus.REJECTED, "cancelled": RequestStatus.CANCELLED}


@_admin_only
def queue_view(request):
    status = request.GET.get("status", "pending")
    if status not in QUEUE_TABS:
        status = "pending"
    counts = {k: sum(m.objects.filter(status=v).count() for m in REQUEST_MODELS.values())
              for k, v in QUEUE_TABS.items()}
    items = _merged(REQUEST_MODELS, _request_row, status=QUEUE_TABS[status])
    if status == "pending":
        items.reverse()  # oldest first: longest-waiting on top
    return render(request, "restrictions/queue.html", {"items": items, "status": status, "counts": counts})


@_admin_only
def review_view(request, kind, pk):
    obj = get_object_or_404(REQUEST_MODELS[_kind(kind)].objects.select_related("resident__profile", "reviewed_by"), pk=pk)
    row = _request_row(kind, obj)
    restricted = (obj.restricted_people if kind == PERSON else obj.restricted_vehicles).first()
    ctx = {"row": row, "r": obj, "kind": kind, "restricted": restricted, "today": timezone.localdate().isoformat(),
           "form": request.session.pop("restriction_review_form", {})}
    return render(request, "restrictions/review.html", ctx)


@_admin_only
@require_POST
def approve_view(request, kind, pk):
    kind = _kind(kind)
    p = request.POST
    try:
        restricted = services.approve_request(
            kind, pk, request.user, remarks=p.get("admin_remarks", ""),
            guard_instructions=p.get("guard_instructions", ""), end_date=p.get("end_date", ""), request=request)
    except RestrictionError as exc:
        messages.error(request, str(exc))
        # keep what the admin typed so a bad end date does not wipe the form
        request.session["restriction_review_form"] = {
            k: p.get(k, "") for k in ("admin_remarks", "guard_instructions", "end_date")}
        return redirect("restrictions:review", kind=kind, pk=pk)
    messages.success(request, f"{services.label(kind, restricted)} is now on the restricted list.")
    return redirect(reverse("restrictions:queue") + "?status=pending")


@_admin_only
@require_POST
def reject_view(request, kind, pk):
    kind = _kind(kind)
    try:
        req = services.reject_request(kind, pk, request.user, remarks=request.POST.get("reason", ""), request=request)
        messages.success(request, f"The request to restrict {services.label(kind, req)} was rejected.")
    except RestrictionError as exc:
        messages.error(request, str(exc))
    return redirect(reverse("restrictions:queue") + "?status=pending")


@_admin_only
def restricted_view(request):
    services.expire_due()
    status = request.GET.get("status", "active")
    if status not in ("active", "ended"):
        status = "active"
    S = RestrictionStatus
    counts = {
        "active": sum(m.objects.filter(status=S.ACTIVE).count() for m in RESTRICTED_MODELS.values()),
        "ended": sum(m.objects.exclude(status=S.ACTIVE).count() for m in RESTRICTED_MODELS.values()),
    }
    if status == "active":
        items = _merged(RESTRICTED_MODELS, _restricted_row, status=S.ACTIVE)
    else:
        items = _merged(RESTRICTED_MODELS, _restricted_row, status__in=[S.INACTIVE, S.REVOKED, S.EXPIRED])
    return render(request, "restrictions/restricted.html", {"items": items, "status": status, "counts": counts})
