from django.contrib.auth.models import User
from django.db import models

from apps.restrictions.models import RestrictedPerson, RestrictedVehicle


class GuardVerificationLog(models.Model):
    """ERD entity GUARD_VERIFICATION_LOG: one lookup a guard made at the gate,
    linked to the restricted person/vehicle it matched (if any)."""

    class VerificationType(models.TextChoices):
        PERSON_SEARCH = "PERSON_SEARCH", "Person search"
        VEHICLE_SEARCH = "VEHICLE_SEARCH", "Vehicle search"

    class MatchResult(models.TextChoices):
        RESTRICTED_MATCH = "RESTRICTED_MATCH", "Restricted match"
        CLEAR_NO_MATCH = "CLEAR_NO_MATCH", "Clear, no match"

    class GateLocation(models.TextChoices):
        MAIN_GATE = "MAIN_GATE", "Main gate"
        SERVICE_GATE = "SERVICE_GATE", "Service gate"
        BASEMENT_GATE = "BASEMENT_GATE", "Basement gate"

    class ActionTaken(models.TextChoices):
        DENIED_ENTRY = "DENIED_ENTRY", "Denied entry"
        ALLOWED_ENTRY = "ALLOWED_ENTRY", "Allowed entry"
        ESCALATED_TO_ADMIN = "ESCALATED_TO_ADMIN", "Escalated to admin"

    guard = models.ForeignKey(User, on_delete=models.PROTECT, related_name="verification_logs")
    verification_type = models.CharField(max_length=20, choices=VerificationType.choices)
    query_input = models.CharField(max_length=150)  # plate number or name searched
    matched_person = models.ForeignKey(
        RestrictedPerson, null=True, blank=True, on_delete=models.SET_NULL, related_name="verification_logs"
    )
    matched_vehicle = models.ForeignKey(
        RestrictedVehicle, null=True, blank=True, on_delete=models.SET_NULL, related_name="verification_logs"
    )
    match_result = models.CharField(max_length=20, choices=MatchResult.choices)
    gate_location = models.CharField(max_length=20, choices=GateLocation.choices)
    action_taken = models.CharField(max_length=30, choices=ActionTaken.choices)
    guard_notes = models.TextField(blank=True)
    verified_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "guard_verification_log"
        ordering = ["-verified_at"]

    def __str__(self):
        return f"{self.query_input} -> {self.match_result}"
