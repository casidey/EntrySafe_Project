from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import render, redirect
from .models import UserSettings


@login_required
def settings_view(request):
    settings, _ = UserSettings.objects.get_or_create(user=request.user)
    if request.method == "POST":
        settings.dark_mode = request.POST.get("dark_mode") == "on"
        settings.email_notifications = request.POST.get("email_notifications") == "on"
        settings.save()
        if request.headers.get("X-Requested-With") == "XMLHttpRequest":
            return JsonResponse({"ok": True, "dark_mode": settings.dark_mode})
        return redirect("user_settings:settings")
    return render(request, "user_settings/user_settings.html", {"settings": settings})
