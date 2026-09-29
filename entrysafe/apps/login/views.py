from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.hashers import check_password
from django.contrib.auth.models import User
from django.shortcuts import render, redirect

from django.db.models import Q

from apps.profile.models import UserProfile

INVALID = "Invalid username/email or password."


def _pending_message(identifier, password):
    """Explain a waiting/declined registration -- but only to someone who knows the password,
    so the login page can't be used to probe which emails have applied."""
    if not identifier:
        return None
    user = (
        User.objects.filter(is_active=False)
        .filter(Q(username__iexact=identifier) | Q(email__iexact=identifier))
        .select_related("profile").first()
    )
    if user is None or not user.check_password(password):
        return None
    profile = getattr(user, "profile", None)
    if profile is None:
        return None
    if profile.approval_status == UserProfile.ApprovalStatus.PENDING:
        return "Your registration is still waiting for administrator approval. You'll be able to sign in once it is approved."
    if profile.approval_status == UserProfile.ApprovalStatus.DISAPPROVED:
        reason = f" Reason: {profile.disapproval_reason.rstrip('. ')}." if profile.disapproval_reason else ""
        return "Your registration was not approved." + reason + " Please contact the building administrator."
    return None


def login_view(request):
    if request.user.is_authenticated:
        return redirect("home:home")

    submitted = request.session.pop("registration_submitted", None)

    if request.method == "POST":
        username = request.POST.get("username", "").strip()
        password = request.POST.get("password", "")

        user = authenticate(request, username=username, password=password)
        if user is None and "@" in username:
            try:
                user_obj = User.objects.get(email=username)
                user = authenticate(request, username=user_obj.username, password=password)
            except (User.DoesNotExist, User.MultipleObjectsReturned):
                pass

        if user is not None:
            login(request, user)
            return redirect("home:home")
        return render(request, "login/login.html", {
            "error": _pending_message(username, password) or INVALID,
            "username": username,
        })
    return render(request, "login/login.html", {"submitted": submitted})


def logout_view(request):
    logout(request)
    return redirect("login:login")
