"""In-app notification feed (Phase 5): every signed-in user sees only their own notifications."""
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from .models import Notification

REQUEST_KINDS = {"PersonRestrictionRequest": "person", "VehicleRestrictionRequest": "vehicle"}
RESTRICTED_KINDS = {"RestrictedPerson", "RestrictedVehicle"}

ICONS = {
    Notification.Type.ACCOUNT_STATUS: "user",
    Notification.Type.REQUEST_STATUS: "list",
    Notification.Type.NEW_RESTRICTION: "shield",
    Notification.Type.GATE_ACTIVITY: "alert",
}


def _role(user):
    if user.is_staff:
        return "admin"
    return "guard" if getattr(getattr(user, "profile", None), "role", "") == "GUARD" else "resident"


def target_url(note, user):
    """The page a notification opens for this user (falls back to the feed)."""
    role, entity = _role(user), note.target_entity
    if entity in REQUEST_KINDS and note.target_id:
        if role == "admin":
            return reverse("restrictions:review", args=[REQUEST_KINDS[entity], note.target_id])
        return reverse("restrictions:mine")
    if entity in RESTRICTED_KINDS:
        return {"admin": reverse("restrictions:restricted"), "guard": reverse("guard:search")}.get(
            role, reverse("restrictions:mine"))
    if entity == "GuardVerificationLog":
        return {"admin": reverse("guard:log"), "guard": reverse("guard:my_checks")}.get(
            role, reverse("restrictions:mine"))
    if entity == "UserProfile":
        return reverse("approvals:registrations") if role == "admin" else reverse("home:home")
    return reverse("notifications:list")


@login_required(login_url="login:login")
def list_view(request):
    show = request.GET.get("show", "all")
    if show not in ("all", "unread"):
        show = "all"
    mine = Notification.objects.filter(recipient=request.user)
    counts = {"all": mine.count(), "unread": mine.filter(is_read=False).count()}
    page = Paginator(mine.filter(is_read=False) if show == "unread" else mine, 20).get_page(request.GET.get("page"))
    items = [{"obj": n, "icon": ICONS.get(n.notification_type, "bell")} for n in page]
    return render(request, "notifications/list.html", {"items": items, "page": page, "show": show, "counts": counts})


@login_required(login_url="login:login")
def open_view(request, pk):
    """Mark one of my notifications as read and go to the page it is about."""
    note = get_object_or_404(Notification, pk=pk, recipient=request.user)
    if not note.is_read:
        note.is_read = True
        note.save(update_fields=["is_read"])
    return redirect(target_url(note, request.user))


@login_required(login_url="login:login")
@require_POST
def mark_all_read_view(request):
    changed = Notification.objects.filter(recipient=request.user, is_read=False).update(is_read=True)
    if changed:
        messages.success(request, f"Marked {changed} notification{'s' if changed != 1 else ''} as read.")
    return redirect("notifications:list")
