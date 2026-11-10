from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render


@login_required(login_url="login:login")
def home_view(request):
    if request.user.is_staff:
        return redirect("approvals:overview")
    from apps.restrictions import services

    profile = getattr(request.user, "profile", None)
    ctx = {"profile": profile, "can_request": services.is_resident(request.user)}
    if ctx["can_request"]:
        ctx["pending_requests"] = services.pending_request_count(resident=request.user)
        ctx["active_restrictions"] = services.active_restriction_count(resident=request.user)
    return render(request, "home/home.html", ctx)
