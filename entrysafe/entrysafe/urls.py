from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path("admin/", admin.site.urls),
    path("login/", include("apps.login.urls")),
    path("register/", include("apps.register.urls")),
    path("profile/", include("apps.profile.urls")),
    path("settings/", include("apps.user_settings.urls")),
    path("", include("apps.home.urls")),
]
