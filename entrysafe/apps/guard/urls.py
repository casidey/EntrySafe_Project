from django.urls import path

from . import views

app_name = "guard"

urlpatterns = [
    path("", views.search_view, name="search"),
    path("record/", views.record_view, name="record"),
    path("checks/", views.my_checks_view, name="my_checks"),
    path("log/", views.verification_log_view, name="log"),
    path("flagged/", views.flagged_view, name="flagged"),
]
