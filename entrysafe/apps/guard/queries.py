"""The two database operations for the JOIN and SUBQUERY activity.

JOIN      gate_log_entries()
          Each gate check together with the guard who recorded it and the restricted
          person or vehicle it matched. Used by the admin "Gate log" page (/guard/log/)
          and the guard's "My checks" page.

SUBQUERY  flagged_people() / flagged_vehicles()
          Restricted people and vehicles that a guard has matched at the gate at least once.
          Used by the admin "Flagged at gate" page (/guard/flagged/).

Run `python manage.py show_sql` to print the SQL Django generates for each one.
"""
from django.db.models import Subquery

from apps.restrictions.models import RestrictedPerson, RestrictedVehicle

from .models import GuardVerificationLog


# ---------------------------------------------------------------- JOIN
def gate_log_entries():
    """JOIN guard_verification_log with the tables it points to:

        guard_verification_log
          INNER JOIN auth_user               ON guard_verification_log.guard_id = auth_user.id
          LEFT  JOIN user_profile            ON user_profile.user_id = auth_user.id
          LEFT  JOIN restricted_person       ON guard_verification_log.matched_person_id = restricted_person.id
          LEFT  JOIN restricted_vehicle      ON guard_verification_log.matched_vehicle_id = restricted_vehicle.id

    select_related() tells Django to fetch all of these in ONE query, so the page can show
    the guard's name and the matched name/plate without a separate query for every row.
    The matched person/vehicle joins are LEFT JOINs because a clear check matches nothing.
    """
    return GuardVerificationLog.objects.select_related("guard__profile", "matched_person", "matched_vehicle")


# ---------------------------------------------------------------- SUBQUERY
def matched_ids(field):
    """Inner query: the ids of restrictions that guards matched at the gate.

        SELECT <field> FROM guard_verification_log WHERE match_result = 'RESTRICTED_MATCH'
    """
    return GuardVerificationLog.objects.filter(
        match_result=GuardVerificationLog.MatchResult.RESTRICTED_MATCH).values(field)


def flagged_people():
    """Outer query: restricted people whose id is in the inner query's result.

        SELECT * FROM restricted_person
        WHERE id IN (SELECT matched_person_id FROM guard_verification_log
                     WHERE match_result = 'RESTRICTED_MATCH')
    """
    return RestrictedPerson.objects.filter(id__in=Subquery(matched_ids("matched_person_id")))


def flagged_vehicles():
    """Outer query: restricted vehicles whose id is in the inner query's result.

        SELECT * FROM restricted_vehicle
        WHERE id IN (SELECT matched_vehicle_id FROM guard_verification_log
                     WHERE match_result = 'RESTRICTED_MATCH')
    """
    return RestrictedVehicle.objects.filter(id__in=Subquery(matched_ids("matched_vehicle_id")))
