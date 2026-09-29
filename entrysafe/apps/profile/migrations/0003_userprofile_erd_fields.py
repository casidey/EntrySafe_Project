import django.db.models.deletion
import django.utils.timezone
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    """Profile -> UserProfile (table user_profile) and add the ERD's approval fields."""

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("profile", "0002_profile_unit_fields_remove_image"),
    ]

    operations = [
        migrations.RenameModel(old_name="Profile", new_name="UserProfile"),
        migrations.AlterModelTable(name="userprofile", table="user_profile"),
        migrations.AddField(
            model_name="userprofile", name="role",
            field=models.CharField(
                choices=[("RESIDENT", "Resident"), ("ADMIN", "Admin"), ("GUARD", "Guard")],
                default="RESIDENT", max_length=20),
        ),
        migrations.AddField(
            model_name="userprofile", name="id_proof_image",
            field=models.FileField(blank=True, upload_to="id_proofs/%Y/%m/"),
        ),
        migrations.AddField(
            model_name="userprofile", name="approval_status",
            field=models.CharField(
                choices=[("PENDING", "Pending"), ("APPROVED", "Approved"), ("DISAPPROVED", "Disapproved")],
                default="PENDING", max_length=20),
        ),
        migrations.AddField(
            model_name="userprofile", name="reviewed_by",
            field=models.ForeignKey(
                blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL,
                related_name="reviewed_profiles", to=settings.AUTH_USER_MODEL),
        ),
        migrations.AddField(
            model_name="userprofile", name="reviewed_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="userprofile", name="disapproval_reason",
            field=models.TextField(blank=True),
        ),
        migrations.AddField(
            model_name="userprofile", name="created_at",
            field=models.DateTimeField(auto_now_add=True, default=django.utils.timezone.now),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="userprofile", name="updated_at",
            field=models.DateTimeField(auto_now=True, default=django.utils.timezone.now),
            preserve_default=False,
        ),
        migrations.AlterField(
            model_name="userprofile", name="unit_number",
            field=models.CharField(blank=True, max_length=60),
        ),
        migrations.AlterField(
            model_name="userprofile", name="contact_number",
            field=models.CharField(blank=True, max_length=40),
        ),
    ]
