from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect
from .models import UserProfile


@login_required
def profile_view(request):
    profile = UserProfile.for_user(request.user)
    if request.method == "POST":
        profile.full_name = request.POST.get("full_name", "").strip()
        profile.contact_number = request.POST.get("contact_number", profile.contact_number).strip()
        profile.save()
        messages.success(request, "Profile saved.")
        return redirect("profile:profile")
    return render(request, "profile/profile.html", {"profile": profile})
