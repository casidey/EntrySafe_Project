"""Guard workflow (Phase 4): look up a name or plate against the ACTIVE restricted list,
then record what happened at the gate (GuardVerificationLog)."""
import re
from functools import wraps
from urllib.parse import urlencode

from django.contrib import messages
from django.contrib.auth.decorators import login_required, user_passes_test
from django.core.paginator import Paginator
from django.db.models import Q, Value
from django.db.models.functions import Replace, Upper
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from apps.profile.models import UserProfile
from apps.restrictions import services
from apps.restrictions.models import RestrictedPerson, RestrictedVehicle, RestrictionStatus

from .models import GuardVerificationLog as Log

MIN_QUERY = 2


def is_guard(user):
    """Active, non-staff account whose profile role is GUARD (guards are created by an admin)."""
    if not user.is_authenticated or not user.is_active or user.is_staff:
        return False
    profile = getattr(user, "profile", None)
    return profile is not None and profile.role == UserProfile.Role.GUARD


def guard_required(view):
    @wraps(view)
    def wrapped(request, *args, **kwargs):
        if not is_guard(request.user):
            return redirect("home:home")
        return view(request, *args, **kwargs)
    return login_required(login_url="login:login")(wrapped)


staff_required = user_passes_test(lambda u: u.is_active and u.is_staff, login_url="login:login")


def admin_required(view):
    return login_required(login_url="login:login")(staff_required(view))


def plate_key(value):
    """'nbx-4471', 'NBX 4471' and 'nbx4471' all become 'NBX4471'."""
    return re.sub(r"[^A-Z0-9]", "", value.upper())


def search_people(query):
    qs = RestrictedPerson.objects.filter(status=RestrictionStatus.ACTIVE)
    for term in query.split():  # every word must match a name or alias
        qs = qs.filter(Q(first_name__icontains=term) | Q(last_name__icontains=term) | Q(alias_nickname__icontains=term))
    return qs


def search_vehicles(query):
    key = plate_key(query)
    if len(key) < MIN_QUERY:
        return RestrictedVehicle.objects.none()
    plate = Replace(Replace(Upper("license_plate"), Value(" "), Value("")), Value("-"), Value(""))
    return RestrictedVehicle.objects.filter(status=RestrictionStatus.ACTIVE).annotate(plate_key=plate).filter(
        plate_key__contains=key)


def _resident_vehicles(query):
    """Residents' own registered vehicles that match the searched plate, so the guard can recognise them."""
    from apps.profile.services import resident_vehicles_matching

    rows = []
    for v in resident_vehicles_matching(query)[:5]:
        p = getattr(v.resident, "profile", None)
        rows.append({"plate": v.license_plate,
                     "detail": " · ".join(b for b in [v.get_vehicle_type_display(), v.make_model, v.color] if b),
                     "owner": (p.full_name if p and p.full_name else v.resident.get_username()),
                     "unit": p.unit_number if p else ""})
    return rows


def _card(kind, obj):
    if kind == services.PERSON:
        detail = " · ".join(b for b in [obj.alias_nickname and f'Also known as "{obj.alias_nickname}"'] if b)
    else:
        detail = " · ".join(b for b in [obj.get_vehicle_type_display(), obj.make_model, obj.color] if b)
    return {"kind": kind, "obj": obj, "title": services.label(kind, obj), "detail": detail,
            "type_label": "Person" if kind == services.PERSON else "Vehicle",
            "icon": "user" if kind == services.PERSON else "list"}


@guard_required
def search_view(request):
    services.expire_due()  # never show a restriction whose end date has passed
    query = " ".join(request.GET.get("q", "").split())[:100]
    searched = len(query) >= MIN_QUERY
    if searched:
        people, vehicles = search_people(query), search_vehicles(query)
    else:
        people = RestrictedPerson.objects.filter(status=RestrictionStatus.ACTIVE)
        vehicles = RestrictedVehicle.objects.filter(status=RestrictionStatus.ACTIVE)
    results = [_card(services.PERSON, o) for o in people] + [_card(services.VEHICLE, o) for o in vehicles]
    results.sort(key=lambda r: r["obj"].created_at, reverse=True)
    from .services import guess_kind

    return render(request, "guard/search.html", {
        "query": query, "searched": searched, "too_short": bool(query) and not searched,
        "results": results, "active_total": services.active_restriction_count(),
        "gates": Log.GateLocation.choices, "actions": Log.ActionTaken.choices,
        "gate": request.session.get("gate_location", Log.GateLocation.MAIN_GATE),
        "clear_kind": guess_kind(query) if searched else services.PERSON,
        "resident_vehicles": _resident_vehicles(query) if searched else [],
    })


@guard_required
@require_POST
def record_view(request):
    """Save the guard's outcome for a match (kind + pk posted) or for a clear search."""
    from .services import VerificationError, record_clear, record_match

    data = request.POST
    query = " ".join(data.get("q", "").split())[:100]
    kind, gate = data.get("kind", ""), data.get("gate_location", "")
    args = (data.get("query_input") or query, gate, data.get("action_taken", ""), data.get("guard_notes", ""))
    try:
        if data.get("pk"):
            log = record_match(request.user, kind, data.get("pk"), *args, request=request)
            what = services.label(kind, log.matched_person or log.matched_vehicle)
        else:
            log = record_clear(request.user, kind, *args, request=request)
            what = f"\u201c{log.query_input}\u201d"
    except (VerificationError, ValueError) as exc:
        messages.error(request, str(exc) if isinstance(exc, VerificationError) else "That restriction was not found.")
    else:
        request.session["gate_location"] = gate  # pre-select the same gate next time
        messages.success(request, f"Recorded: {log.get_action_taken_display().lower()} for {what} "
                                  f"at the {log.get_gate_location_display()}.")
    url = reverse("guard:search")
    return redirect(f"{url}?{urlencode({'q': query})}" if query else url)


def _log_row(log):
    from .services import matched_label

    restricted = log.match_result == Log.MatchResult.RESTRICTED_MATCH
    action_pill = {Log.ActionTaken.DENIED_ENTRY: "red", Log.ActionTaken.ALLOWED_ENTRY: "green"}.get(log.action_taken, "")
    guard_profile = getattr(log.guard, "profile", None)
    return {
        "obj": log, "restricted": restricted, "matched": matched_label(log),
        "icon": "user" if log.verification_type == Log.VerificationType.PERSON_SEARCH else "list",
        "action_pill": action_pill,
        "guard_name": (guard_profile.full_name if guard_profile and guard_profile.full_name else "")
        or log.guard.get_username(),
    }


def _logs():
    return Log.objects.select_related("guard__profile", "matched_person", "matched_vehicle")


@guard_required
def my_checks_view(request):
    """The signed-in guard's own recent gate checks."""
    logs = _logs().filter(guard=request.user)
    today = logs.filter(verified_at__date=timezone.localdate())
    return render(request, "guard/my_checks.html", {
        "items": [_log_row(x) for x in logs[:50]],
        "today_total": today.count(),
        "today_restricted": today.filter(match_result=Log.MatchResult.RESTRICTED_MATCH).count(),
    })


@admin_required
def verification_log_view(request):
    """Every gate check, newest first, filterable by result, action and gate."""
    result = request.GET.get("result", "all")
    if result not in ("all", "restricted", "clear"):
        result = "all"
    action = request.GET.get("action", "")
    gate = request.GET.get("gate", "")
    action = action if action in Log.ActionTaken.values else ""
    gate = gate if gate in Log.GateLocation.values else ""

    base = _logs()
    if action:
        base = base.filter(action_taken=action)
    if gate:
        base = base.filter(gate_location=gate)
    counts = {
        "all": base.count(),
        "restricted": base.filter(match_result=Log.MatchResult.RESTRICTED_MATCH).count(),
        "clear": base.filter(match_result=Log.MatchResult.CLEAR_NO_MATCH).count(),
    }
    qs = {"restricted": base.filter(match_result=Log.MatchResult.RESTRICTED_MATCH),
          "clear": base.filter(match_result=Log.MatchResult.CLEAR_NO_MATCH)}.get(result, base)
    page = Paginator(qs, 25).get_page(request.GET.get("page"))
    keep = {k: v for k, v in (("action", action), ("gate", gate)) if v}
    return render(request, "guard/verification_log.html", {
        "items": [_log_row(x) for x in page], "page": page, "counts": counts, "result": result,
        "action": action, "gate": gate, "actions": Log.ActionTaken.choices, "gates": Log.GateLocation.choices,
        "filter_qs": urlencode(keep), "page_qs": urlencode({**keep, "result": result}),
    })
