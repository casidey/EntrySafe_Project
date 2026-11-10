from django.urls import path

from . import views

app_name = "restrictions"

urlpatterns = [
    # resident
    path("", views.my_requests_view, name="mine"),
    path("<str:kind>/new/", views.new_request_view, name="new"),
    path("<str:kind>/<int:pk>/cancel/", views.cancel_view, name="cancel"),
    path("<str:kind>/<int:pk>/photo/", views.request_photo_view, name="request_photo"),
    # resident (own) or admin
    path("restricted/<str:kind>/<int:pk>/remove/", views.remove_view, name="remove"),
    path("restricted/<str:kind>/<int:pk>/photo/", views.restricted_photo_view, name="restricted_photo"),
    # admin
    path("review/", views.queue_view, name="queue"),
    path("review/<str:kind>/<int:pk>/", views.review_view, name="review"),
    path("review/<str:kind>/<int:pk>/approve/", views.approve_view, name="approve"),
    path("review/<str:kind>/<int:pk>/reject/", views.reject_view, name="reject"),
    path("restricted/", views.restricted_view, name="restricted"),
]
