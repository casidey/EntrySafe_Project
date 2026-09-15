from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect
from .models import UserSettings


@login_required
def settings_view(request):
    settings, _ = UserSettings.objects.get_or_create(user=request.user)
    if request.method == "POST":
        settings.dark_mode = request.POST.get("dark_mode") == "on"
        settings.email_notifications = request.POST.get("email_notifications") == "on"
        settings.save()
        return redirect("user_settings:settings")
    return render(request, "user_settings/user_settings.html", {"settings": settings})
