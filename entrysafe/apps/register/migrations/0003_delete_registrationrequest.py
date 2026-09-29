from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [("register", "0002_move_pending_requests_to_profiles")]
    operations = [migrations.DeleteModel(name="RegistrationRequest")]
