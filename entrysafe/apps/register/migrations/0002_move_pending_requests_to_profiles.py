from django.db import migrations


def move(apps, schema_editor):
    """Registration requests that were still waiting (or rejected) become an inactive user
    with a PENDING/DISAPPROVED profile, so nothing submitted earlier is lost."""
    Old = apps.get_model("register", "RegistrationRequest")
    User = apps.get_model("auth", "User")
    UserProfile = apps.get_model("profile", "UserProfile")
    for r in Old.objects.exclude(status="approved"):
        if User.objects.filter(username=r.username).exists():
            continue
        user = User.objects.create(username=r.username, email=r.email, first_name=r.full_name[:150],
                                   password=r.password_hash, is_active=False)
        UserProfile.objects.create(
            user=user, role="RESIDENT", full_name=r.full_name, contact_number=r.contact_number,
            unit_number=f"Tower {r.tower}, Unit {r.unit_number}".replace("Unit Unit", "Unit"),
            id_proof_image=r.proof_document.name if r.proof_document else "",
            approval_status="PENDING" if r.status == "pending" else "DISAPPROVED",
        )


class Migration(migrations.Migration):
    dependencies = [
        ("register", "0001_initial"),
        ("profile", "0005_remove_non_erd_fields"),
    ]
    operations = [migrations.RunPython(move, migrations.RunPython.noop)]
