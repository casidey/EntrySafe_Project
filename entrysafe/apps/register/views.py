from django.contrib.auth.models import User
from django.shortcuts import render, redirect
from apps.profile.models import Profile


def register_view(request):
    if request.user.is_authenticated:
        return redirect("home:home")

    if request.method == "POST":
        full_name = request.POST.get("fullName", "").strip()
        email = request.POST.get("emailAddress", "").strip()
        username = request.POST.get("username", "").strip() or email or full_name.lower().replace(" ", "_")
        password = request.POST.get("password", "")

        if not password or (not email and not username):
            return render(request, "register/register.html", {
                "error": "Please provide your name, email, and password."
            })

        if User.objects.filter(username=username).exists() or (email and User.objects.filter(email=email).exists()):
            return render(request, "register/register.html", {
                "error": "An account with this username or email already exists."
            })

        user = User.objects.create_user(
            username=username,
            email=email,
            password=password,
            first_name=full_name
        )
        Profile.objects.get_or_create(user=user, defaults={"full_name": full_name})
        return redirect("login:login")

    return render(request, "register/register.html")
