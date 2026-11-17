"""Gate verification (Phase 4 part 2): the guard records what happened at the gate.

    restricted match -> GuardVerificationLog (RESTRICTED_MATCH) linked to the restriction,
                        the resident who filed it is notified, admins too when the guard
                        escalated or let the person/vehicle in anyway
    clear search     -> GuardVerificationLog (CLEAR_NO_MATCH), nobody is notified

Every record also writes an AuditLog row.
"""
from django.db import transaction

from apps.audit.models import AuditLog
from apps.notifications.models import Notification
from apps.restrictions import services as restrictions
from apps.restrictions.models import RestrictionStatus

from .models import GuardVerificationLog

Log = GuardVerificationLog
MAX_NOTES = 1000
MAX_QUERY = 150

# the restriction kind a search was about -> ERD verification_type
VERIFICATION_TYPES = {
    restrictions.PERSON: Log.VerificationType.PERSON_SEARCH,
    restrictions.VEHICLE: Log.VerificationType.VEHICLE_SEARCH,
}


class VerificationError(Exception):
    """The outcome could not be recorded (bad input, restriction no longer active)."""


def guess_kind(query):
    """Plates have digits and names do not, so pre-select the search type for a clear result."""
    return restrictions.VEHICLE if any(c.isdigit() for c in query) else restrictions.PERSON


def _clean(query, gate_location, action_taken, notes):
    query = " ".join((query or "").split())
    notes = (notes or "").strip()
    if not query:
        raise VerificationError("There is no search to record. Search a name or plate first.")
    if len(query) > MAX_QUERY:
        raise VerificationError("The search text is too long to record.")
    if gate_location not in Log.GateLocation.values:
        raise VerificationError("Please choose the gate you are at.")
    if action_taken not in Log.ActionTaken.values:
        raise VerificationError("Please choose the action you took.")
    if len(notes) > MAX_NOTES:
        raise VerificationError(f"Notes are too long ({MAX_NOTES} characters at most).")
    return query, notes


def _owner(restricted):
    """The resident who filed the request behind a restriction (None if added directly)."""
    req = restricted.request
    return req.resident if req is not None else None


def record_match(guard, kind, pk, query, gate_location, action_taken, notes="", request=None):
    """Log the outcome for a search that matched an ACTIVE restriction."""
    if kind not in restrictions.KINDS:
        raise VerificationError("Unknown restriction type.")
    query, notes = _clean(query, gate_location, action_taken, notes)
    restrictions.expire_due()
    model = restrictions.RESTRICTED_MODELS[kind]
    with transaction.atomic():
        restricted = model.objects.select_related("request__resident").filter(pk=pk).first()
        if restricted is None or restricted.status != RestrictionStatus.ACTIVE:
            raise VerificationError("That restriction is no longer active. Search again before recording.")
        log = Log.objects.create(
            guard=guard,
            verification_type=VERIFICATION_TYPES[kind],
            query_input=query,
            matched_person=restricted if kind == restrictions.PERSON else None,
            matched_vehicle=restricted if kind == restrictions.VEHICLE else None,
            match_result=Log.MatchResult.RESTRICTED_MATCH,
            gate_location=gate_location,
            action_taken=action_taken,
            guard_notes=notes,
        )
        name = restrictions.label(kind, restricted)
        action = log.get_action_taken_display().lower()
        gate = log.get_gate_location_display()
        AuditLog.record(guard, AuditLog.Action.RECORD_VERIFICATION, "GuardVerificationLog", log.pk,
                        f"Restricted match for {name} at the {gate}: {action}.", request)

        owner = _owner(restricted)
        if owner is not None:
            restrictions._notify([owner], f"Gate check: {name}",
                                 f"A guard checked {name} at the {gate} and recorded: {action}.",
                                 Notification.Type.GATE_ACTIVITY, "GuardVerificationLog", log.pk)
        if action_taken in (Log.ActionTaken.ESCALATED_TO_ADMIN, Log.ActionTaken.ALLOWED_ENTRY):
            title = ("Gate escalation" if action_taken == Log.ActionTaken.ESCALATED_TO_ADMIN
                     else "Restricted entry allowed")
            restrictions._notify(restrictions._admins(), f"{title}: {name}",
                                 f"{_guard_name(guard)} recorded {action} for {name} at the {gate}."
                                 + (f" Notes: {notes}" if notes else ""),
                                 Notification.Type.GATE_ACTIVITY, "GuardVerificationLog", log.pk)
    return log


def record_clear(guard, kind, query, gate_location, action_taken, notes="", request=None):
    """Log the outcome for a search with no active match. Refused if the search does match."""
    if kind not in restrictions.KINDS:
        raise VerificationError("Please choose whether you checked a person or a vehicle.")
    query, notes = _clean(query, gate_location, action_taken, notes)
    from .views import search_people, search_vehicles  # same matching rules as the Gate check page

    restrictions.expire_due()
    if search_people(query).exists() or search_vehicles(query).exists():
        raise VerificationError("This search matches an active restriction. Record the outcome on the match instead.")
    with transaction.atomic():
        log = Log.objects.create(
            guard=guard, verification_type=VERIFICATION_TYPES[kind], query_input=query,
            match_result=Log.MatchResult.CLEAR_NO_MATCH, gate_location=gate_location,
            action_taken=action_taken, guard_notes=notes,
        )
        AuditLog.record(guard, AuditLog.Action.RECORD_VERIFICATION, "GuardVerificationLog", log.pk,
                        f"Clear check for \"{query}\" at the {log.get_gate_location_display()}: "
                        f"{log.get_action_taken_display().lower()}.", request)
        if action_taken == Log.ActionTaken.ESCALATED_TO_ADMIN:
            restrictions._notify(restrictions._admins(), f"Gate escalation: {query}",
                                 f"{_guard_name(guard)} escalated a clear check for \"{query}\" at the "
                                 f"{log.get_gate_location_display()}." + (f" Notes: {notes}" if notes else ""),
                                 Notification.Type.GATE_ACTIVITY, "GuardVerificationLog", log.pk)
    return log


def _guard_name(user):
    profile = getattr(user, "profile", None)
    return (profile.full_name if profile and profile.full_name else "") or user.get_full_name() or user.get_username()


def matched_label(log):
    """Name or plate of the restriction a log entry matched ('' for clear checks)."""
    if log.matched_person_id:
        return restrictions.label(restrictions.PERSON, log.matched_person)
    if log.matched_vehicle_id:
        return restrictions.label(restrictions.VEHICLE, log.matched_vehicle)
    return ""
