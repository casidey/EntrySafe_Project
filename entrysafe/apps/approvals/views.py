import mimetypes

from django.contrib import messages
from django.contrib.auth.decorators import login_required, user_passes_test
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from apps.profile.models import ReviewError, UserProfile
from apps.restrictions import services as restriction_services

# Administrators are Django staff users (created with `createsuperuser`).
staff_required = user_passes_test(lambda u: u.is_active and u.is_staff, login_url="login:login")


def _guard(view):
    return login_required(login_url="login:login")(staff_required(view))


def _residents():
    return UserProfile.objects.filter(role=UserProfile.Role.RESIDENT, user__is_staff=False).select_related(
        "user", "reviewed_by")


@_guard
def overview_view(request):
    qs = _residents()
    S = UserProfile.ApprovalStatus
    ctx = {
        "pending_count": qs.filter(approval_status=S.PENDING).count(),
        "approved_count": qs.filter(approval_status=S.APPROVED).count(),
        "rejected_count": qs.filter(approval_status=S.DISAPPROVED).count(),
        "recent": qs.exclude(approval_status=S.PENDING).order_by("-reviewed_at")[:5],
        "latest_pending": qs.filter(approval_status=S.PENDING).order_by("created_at")[:3],
        "pending_requests_count": restriction_services.pending_request_count(),
        "active_restrictions_count": restriction_services.active_restriction_count(),
    }
    return render(request, "approvals/overview.html", ctx)


@_guard
def registrations_view(request):
    S = UserProfile.ApprovalStatus
    tabs = {"pending": S.PENDING, "approved": S.APPROVED, "disapproved": S.DISAPPROVED}
    status = request.GET.get("status", "pending")
    if status not in tabs:
        status = "pending"
    counts = {k: _residents().filter(approval_status=v).count() for k, v in tabs.items()}
    items = _residents().filter(approval_status=tabs[status])
    return render(request, "approvals/registrations.html", {"items": items, "status": status, "counts": counts})


def _review(request, pk, action):
    profile = get_object_or_404(_residents(), pk=pk)
    name = profile.full_name or profile.user.username
    try:
        if action == "approve":
            profile.approve(request.user, request=request)
            messages.success(request, f"{name} was approved and can now sign in.")
        else:
            profile.disapprove(request.user, reason=request.POST.get("reason", ""), request=request)
            messages.success(request, f"{name}'s registration was disapproved.")
    except ReviewError as exc:
        messages.error(request, str(exc))
    return redirect(reverse("approvals:registrations") + "?status=pending")


@_guard
@require_POST
def approve_view(request, pk):
    return _review(request, pk, "approve")


@_guard
@require_POST
def disapprove_view(request, pk):
    return _review(request, pk, "disapprove")


@_guard
def proof_view(request, pk):
    profile = get_object_or_404(UserProfile, pk=pk)
    if not profile.id_proof_image:
        raise Http404("No document on file.")
    try:
        fh = profile.id_proof_image.open("rb")
    except FileNotFoundError:
        raise Http404("Document is missing from storage.")
    ctype = mimetypes.guess_type(profile.id_proof_image.name)[0] or "application/octet-stream"
    return FileResponse(fh, content_type=ctype)
