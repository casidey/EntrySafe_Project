from django.db import migrations


class Migration(migrations.Migration):
    """Drop columns that are not part of the ERD's USER_PROFILE."""

    dependencies = [("profile", "0004_backfill_existing_profiles")]
    operations = [
        migrations.RemoveField(model_name="userprofile", name="bio"),
        migrations.RemoveField(model_name="userprofile", name="tower"),
        migrations.RemoveField(model_name="userprofile", name="occupancy_type"),
    ]
