from django.urls import path

from . import views

app_name = "profile"

urlpatterns = [
    path("", views.profile_view, name="profile"),
    path("password/", views.password_view, name="password"),
    path("vehicles/add/", views.vehicle_add_view, name="vehicle_add"),
    path("vehicles/<int:pk>/remove/", views.vehicle_remove_view, name="vehicle_remove"),
]
