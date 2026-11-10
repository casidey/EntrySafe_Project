"""Guard workflow (Phase 4): look up a name or plate against the ACTIVE restricted list."""
import re
from functools import wraps

from django.contrib.auth.decorators import login_required
from django.db.models import Q, Value
from django.db.models.functions import Replace, Upper
from django.shortcuts import redirect, render

from apps.profile.models import UserProfile
from apps.restrictions import services
from apps.restrictions.models import RestrictedPerson, RestrictedVehicle, RestrictionStatus

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
    return render(request, "guard/search.html", {
        "query": query, "searched": searched, "too_short": bool(query) and not searched,
        "results": results, "active_total": services.active_restriction_count(),
    })
