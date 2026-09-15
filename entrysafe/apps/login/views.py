from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.models import User
from django.shortcuts import render, redirect


def login_view(request):
    if request.user.is_authenticated:
        return redirect("home:home")

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
            "error": "Invalid username/email or password."
        })
    return render(request, "login/login.html")


def logout_view(request):
    logout(request)
    return redirect("login:login")
