from django.contrib.auth.models import User
from django.db import models

VEHICLE_TYPES = [
    ("SEDAN", "Sedan"),
    ("SUV", "SUV"),
    ("MOTORCYCLE", "Motorcycle"),
    ("VAN", "Van"),
    ("TRUCK", "Truck"),
]


class RequestStatus(models.TextChoices):
    PENDING = "PENDING", "Pending"
    APPROVED = "APPROVED", "Approved"
    REJECTED = "REJECTED", "Rejected"
    CANCELLED = "CANCELLED", "Cancelled"


class RestrictionStatus(models.TextChoices):
    ACTIVE = "ACTIVE", "Active"
    INACTIVE = "INACTIVE", "Inactive"
    REVOKED = "REVOKED", "Revoked"
    EXPIRED = "EXPIRED", "Expired"


class PersonRestrictionRequest(models.Model):
    """ERD entity PERSON_RESTRICTION_REQUEST: a resident asks to restrict a person."""

    resident = models.ForeignKey(User, on_delete=models.CASCADE, related_name="person_restriction_requests")
    first_name = models.CharField(max_length=80)
    last_name = models.CharField(max_length=80)
    alias_nickname = models.CharField(max_length=80, blank=True)
    relationship_to_resident = models.CharField(max_length=80, blank=True)  # e.g. ex-tenant, contractor, visitor
    reason = models.TextField()
    photo = models.ImageField(upload_to="restriction_photos/persons/%Y/%m/", blank=True)
    status = models.CharField(max_length=20, choices=RequestStatus.choices, default=RequestStatus.PENDING)
    reviewed_by = models.ForeignKey(
        User, null=True, blank=True, on_delete=models.SET_NULL, related_name="reviewed_person_requests"
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    admin_remarks = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "person_restriction_request"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.first_name} {self.last_name} ({self.status})"


class VehicleRestrictionRequest(models.Model):
    """ERD entity VEHICLE_RESTRICTION_REQUEST: a resident asks to restrict a vehicle."""

    resident = models.ForeignKey(User, on_delete=models.CASCADE, related_name="vehicle_restriction_requests")
    license_plate = models.CharField(max_length=20)
    vehicle_type = models.CharField(max_length=20, choices=VEHICLE_TYPES)
    make_model = models.CharField(max_length=100, blank=True)  # e.g. Toyota Vios
    color = models.CharField(max_length=40, blank=True)
    photo = models.ImageField(upload_to="restriction_photos/vehicles/%Y/%m/", blank=True)
    reason = models.TextField()
    status = models.CharField(max_length=20, choices=RequestStatus.choices, default=RequestStatus.PENDING)
    reviewed_by = models.ForeignKey(
        User, null=True, blank=True, on_delete=models.SET_NULL, related_name="reviewed_vehicle_requests"
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    admin_remarks = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "vehicle_restriction_request"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.license_plate} ({self.status})"


class RestrictedPerson(models.Model):
    """ERD entity RESTRICTED_PERSON: an active/ended restriction on a person.
    Created when an admin approves a PersonRestrictionRequest (request is null if added directly)."""

    request = models.ForeignKey(
        PersonRestrictionRequest, null=True, blank=True, on_delete=models.SET_NULL, related_name="restricted_people"
    )
    approved_by = models.ForeignKey(
        User, null=True, blank=True, on_delete=models.SET_NULL, related_name="authorized_restricted_people"
    )
    first_name = models.CharField(max_length=80)
    last_name = models.CharField(max_length=80)
    alias_nickname = models.CharField(max_length=80, blank=True)
    photo = models.ImageField(upload_to="restricted/persons/%Y/%m/", blank=True)
    restriction_reason = models.TextField()
    guard_instructions = models.TextField(blank=True)  # orders for security guards at the entrance
    status = models.CharField(max_length=20, choices=RestrictionStatus.choices, default=RestrictionStatus.ACTIVE)
    start_date = models.DateField()
    end_date = models.DateField(null=True, blank=True)  # null = permanent
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "restricted_person"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.first_name} {self.last_name} ({self.status})"


class RestrictedVehicle(models.Model):
    """ERD entity RESTRICTED_VEHICLE: an active/ended restriction on a vehicle.
    Created when an admin approves a VehicleRestrictionRequest (request is null if added directly)."""

    request = models.ForeignKey(
        VehicleRestrictionRequest, null=True, blank=True, on_delete=models.SET_NULL, related_name="restricted_vehicles"
    )
    approved_by = models.ForeignKey(
        User, null=True, blank=True, on_delete=models.SET_NULL, related_name="authorized_restricted_vehicles"
    )
    license_plate = models.CharField(max_length=20)
    vehicle_type = models.CharField(max_length=20, choices=VEHICLE_TYPES)
    make_model = models.CharField(max_length=100, blank=True)
    color = models.CharField(max_length=40, blank=True)
    photo = models.ImageField(upload_to="restricted/vehicles/%Y/%m/", blank=True)
    restriction_reason = models.TextField()
    guard_instructions = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=RestrictionStatus.choices, default=RestrictionStatus.ACTIVE)
    start_date = models.DateField()
    end_date = models.DateField(null=True, blank=True)  # null = permanent
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "restricted_vehicle"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.license_plate} ({self.status})"
