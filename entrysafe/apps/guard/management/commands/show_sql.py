"""Print the SQL that Django generates for the JOIN and the SUBQUERY (activity Step 17).

    python manage.py show_sql

The SQL matches whichever database is configured: SQLite locally, PostgreSQL when
DATABASE_URL points at Supabase. You can paste the printed statements into the
Supabase SQL Editor (put quotes around text values such as 'RESTRICTED_MATCH').
"""
import sqlparse
from django.core.management.base import BaseCommand
from django.db import connection

from apps.guard import queries


class Command(BaseCommand):
    help = "Print the SQL generated for the JOIN (gate log) and the SUBQUERY (flagged at gate)."

    def show(self, title, qs):
        self.stdout.write(self.style.MIGRATE_HEADING(f"\n{title}"))
        self.stdout.write(sqlparse.format(str(qs.query), reindent=True, keyword_case="upper"))
        self.stdout.write(f"-- rows returned: {qs.count()}")

    def handle(self, *args, **options):
        self.stdout.write(f"Database: {connection.vendor}")
        self.show("JOIN: gate log entries with guard and matched restriction  (queries.gate_log_entries)",
                  queries.gate_log_entries())
        self.show("SUBQUERY: restricted people matched at the gate  (queries.flagged_people)",
                  queries.flagged_people())
        self.show("SUBQUERY: restricted vehicles matched at the gate  (queries.flagged_vehicles)",
                  queries.flagged_vehicles())
