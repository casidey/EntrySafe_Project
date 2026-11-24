from django.urls import path

from . import views

app_name = "approvals"

urlpatterns = [
    path("", views.overview_view, name="overview"),
    path("registrations/", views.registrations_view, name="registrations"),
    path("registrations/<int:pk>/approve/", views.approve_view, name="approve"),
    path("registrations/<int:pk>/disapprove/", views.disapprove_view, name="disapprove"),
    path("registrations/<int:pk>/proof/", views.proof_view, name="proof"),
    path("accounts/", views.accounts_view, name="accounts"),
    path("accounts/<int:pk>/", views.account_edit_view, name="account_edit"),
    path("accounts/<int:pk>/status/", views.account_status_view, name="account_status"),
    path("audit/", views.audit_view, name="audit"),
    path("search/", views.search_view, name="search"),
]
