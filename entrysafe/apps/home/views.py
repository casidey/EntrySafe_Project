from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render


@login_required(login_url="login:login")
def home_view(request):
    if request.user.is_staff:
        return redirect("approvals:overview")
    profile = getattr(request.user, "profile", None)
    return render(request, "home/home.html", {"profile": profile})
