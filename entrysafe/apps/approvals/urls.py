from django.urls import path

from . import views

app_name = "approvals"

urlpatterns = [
    path("", views.overview_view, name="overview"),
    path("registrations/", views.registrations_view, name="registrations"),
    path("registrations/<int:pk>/approve/", views.approve_view, name="approve"),
    path("registrations/<int:pk>/disapprove/", views.disapprove_view, name="disapprove"),
    path("registrations/<int:pk>/proof/", views.proof_view, name="proof"),
]
