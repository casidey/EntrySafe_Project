"""Admin search across records (Phase 5): one query over restrictions, requests, residents and the gate log."""
from django.db.models import Q
from django.urls import reverse

from apps.guard.models import GuardVerificationLog
from apps.guard.views import plate_key
from apps.profile.models import UserProfile
from apps.restrictions.models import (
    PersonRestrictionRequest, RequestStatus, RestrictedPerson, RestrictedVehicle, RestrictionStatus,
    VehicleRestrictionRequest)

LIMIT = 10
MIN_QUERY = 2


def _words(qs, query, fields):
    """Every word of the query must appear in at least one of the fields."""
    for term in query.split():
        cond = Q()
        for f in fields:
            cond |= Q(**{f"{f}__icontains": term})
        qs = qs.filter(cond)
    return qs


def _plates(qs, query, extra_fields):
    """Vehicles: match the plate ignoring spaces/dashes/case, or every word in the other fields."""
    key = plate_key(query)
    ids = [pk for pk, plate in qs.values_list("pk", "license_plate") if key and key in plate_key(plate)]
    return qs.filter(Q(pk__in=ids) | Q(pk__in=_words(qs, query, extra_fields).values("pk")))


def _group(title, icon, qs, row):
    total = qs.count()
    return {"title": title, "icon": icon, "total": total, "rows": [row(o) for o in qs[:LIMIT]]}


def _restricted_link(obj):
    ended = "active" if obj.status == RestrictionStatus.ACTIVE else "ended"
    return reverse("restrictions:restricted") + f"?status={ended}"


def search(query):
    query = " ".join(query.split())
    if len(query) < MIN_QUERY:
        return []
    person_fields = ["first_name", "last_name", "alias_nickname"]
    vehicle_fields = ["make_model", "color"]
    groups = [
        _group("Restricted people", "shield",
               _words(RestrictedPerson.objects.all(), query, person_fields + ["restriction_reason"]),
               lambda o: {"title": f"{o.first_name} {o.last_name}", "sub": o.alias_nickname and f'Also known as "{o.alias_nickname}"',
                          "pill": o.get_status_display(), "red": o.status == RestrictionStatus.ACTIVE,
                          "url": _restricted_link(o)}),
        _group("Restricted vehicles", "shield",
               _plates(RestrictedVehicle.objects.all(), query, vehicle_fields + ["restriction_reason"]),
               lambda o: {"title": o.license_plate, "sub": " · ".join(b for b in [o.get_vehicle_type_display(), o.make_model, o.color] if b),
                          "pill": o.get_status_display(), "red": o.status == RestrictionStatus.ACTIVE,
                          "url": _restricted_link(o)}),
        _group("Person requests", "list",
               _words(PersonRestrictionRequest.objects.select_related("resident__profile"), query,
                      person_fields + ["reason", "resident__profile__full_name"]),
               lambda o: _request_row("person", o, f"{o.first_name} {o.last_name}")),
        _group("Vehicle requests", "list",
               _plates(VehicleRestrictionRequest.objects.select_related("resident__profile"), query,
                       vehicle_fields + ["reason", "resident__profile__full_name"]),
               lambda o: _request_row("vehicle", o, o.license_plate)),
        _group("Residents", "user",
               _words(UserProfile.objects.filter(role=UserProfile.Role.RESIDENT, user__is_staff=False)
                      .select_related("user"), query,
                      ["full_name", "unit_number", "contact_number", "user__username", "user__email"]),
               lambda o: {"title": o.full_name or o.user.username,
                          "sub": " · ".join(b for b in [o.unit_number, o.user.email] if b),
                          "pill": o.get_approval_status_display(),
                          "red": o.approval_status == UserProfile.ApprovalStatus.DISAPPROVED,
                          "url": reverse("approvals:registrations") + f"?status={_reg_tab(o)}"}),
        _group("Gate log", "eye",
               _words(GuardVerificationLog.objects.select_related("guard"), query,
                      ["query_input", "guard_notes", "matched_person__first_name", "matched_person__last_name",
                       "matched_vehicle__license_plate"]),
               lambda o: {"title": f"“{o.query_input}”",
                          "sub": f"{o.get_gate_location_display()} · {o.get_action_taken_display()} · {o.verified_at:%b %d, %Y}",
                          "pill": "Restricted" if o.match_result == GuardVerificationLog.MatchResult.RESTRICTED_MATCH else "Clear",
                          "red": o.match_result == GuardVerificationLog.MatchResult.RESTRICTED_MATCH,
                          "url": reverse("guard:log")}),
    ]
    return groups


def _request_row(kind, obj, title):
    profile = getattr(obj.resident, "profile", None)
    by = (profile.full_name if profile and profile.full_name else obj.resident.get_username())
    return {"title": title, "sub": f"From {by} · {obj.created_at:%b %d, %Y}", "pill": obj.get_status_display(),
            "red": obj.status == RequestStatus.REJECTED, "url": reverse("restrictions:review", args=[kind, obj.pk])}


def _reg_tab(profile):
    S = UserProfile.ApprovalStatus
    return {S.PENDING: "pending", S.APPROVED: "approved", S.DISAPPROVED: "disapproved"}.get(profile.approval_status, "pending")
