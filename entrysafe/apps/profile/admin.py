from django.contrib import admin

from .models import ResidentVehicle, UserProfile


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "full_name", "role", "unit_number", "approval_status", "created_at")
    list_filter = ("role", "approval_status")
    search_fields = ("user__username", "user__email", "full_name", "unit_number")


@admin.register(ResidentVehicle)
class ResidentVehicleAdmin(admin.ModelAdmin):
    list_display = ("license_plate", "resident", "vehicle_type", "make_model", "color")
    search_fields = ("license_plate", "resident__username", "resident__profile__full_name")
