from django.db import migrations


def backfill(apps, schema_editor):
    """Profiles that already exist belong to people who could sign in, so they are APPROVED.
    Tower + unit are folded into the single ERD column unit_number."""
    UserProfile = apps.get_model("profile", "UserProfile")
    for p in UserProfile.objects.select_related("user"):
        p.approval_status = "APPROVED"
        p.role = "ADMIN" if p.user.is_staff else "RESIDENT"
        unit = (p.unit_number or "").strip()
        if p.tower:
            unit = f"Tower {p.tower}, " + (unit if unit.lower().startswith("unit") or not unit else f"Unit {unit}")
            p.unit_number = unit.rstrip(", ")
        p.save(update_fields=["approval_status", "role", "unit_number"])


class Migration(migrations.Migration):
    dependencies = [("profile", "0003_userprofile_erd_fields")]
    operations = [migrations.RunPython(backfill, migrations.RunPython.noop)]
