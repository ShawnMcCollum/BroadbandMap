from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("bdc", "0001_initial"),
        ("served_unserved", "0005_placement_per_release"),
    ]

    operations = [
        migrations.DeleteModel(name="Location"),
    ]
