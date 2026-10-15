"""Store each location's block and H3 cell on its statuses, and make location_id a plain integer.

Written by hand (ADR 0012). The generated migration would drop and re-add location_id, losing the
loaded statuses. This one keeps them, filling block and cell from bdc_location, which
bdc 0002_delete_location then drops.
"""

import django.db.models.deletion
from django.db import migrations, models

# Copy each location's block and cell onto its statuses.
FILL_PLACEMENT = """
UPDATE served_unserved_servedstatus AS s
SET block_id = l.block_id, h3_res8 = l.h3_res8
FROM bdc_location AS l
WHERE l.location_id = s.location_id
"""

# Undo: one bdc_location row per location, placed as in its latest release (latest as_of, then
# latest processed_on, as Release orders them).
RESTORE_LOCATIONS = """
INSERT INTO bdc_location (location_id, block_id, h3_res8)
SELECT DISTINCT ON (s.location_id) s.location_id, s.block_id, s.h3_res8
FROM served_unserved_servedstatus AS s
JOIN bdc_release AS r ON r.id = s.release_id
ORDER BY s.location_id, r.as_of DESC, r.processed_on DESC
"""

BLOCK_HELP = "2020 census block containing the location in this release (block_geoid)."
H3_HELP = "H3 resolution-8 cell index of the location in this release, lowercase hex (h3_res8_id)."
LOCATION_ID_HELP = "FCC location ID from the Broadband Serviceable Location Fabric."


class Migration(migrations.Migration):
    dependencies = [
        ("bdc", "0001_initial"),
        ("geography", "0002_block_place_county_subdivision"),
        ("served_unserved", "0004_rollup_place_levels"),
    ]

    operations = [
        # The unique constraint, and below the location_id index and foreign key, go before the
        # fill so it does not update them row by row (239 s against 72 s for Ohio). The index
        # and the constraint are rebuilt after the fill.
        migrations.RemoveConstraint(
            model_name="servedstatus",
            name="served_unserved_unique_location_per_release",
        ),
        # location becomes the plain integer location_id. In the database only the foreign key
        # constraint and the index are dropped; the column keeps its name and data.
        migrations.SeparateDatabaseAndState(
            database_operations=[
                migrations.AlterField(
                    model_name="servedstatus",
                    name="location",
                    field=models.BigIntegerField(db_column="location_id"),
                ),
            ],
            state_operations=[
                migrations.RemoveField(model_name="servedstatus", name="location"),
                migrations.AddField(
                    model_name="servedstatus",
                    name="location_id",
                    field=models.BigIntegerField(help_text=LOCATION_ID_HELP),
                ),
            ],
        ),
        # Nullable, and without a foreign key constraint, until filled
        migrations.AddField(
            model_name="servedstatus",
            name="block",
            field=models.ForeignKey(
                db_constraint=False,
                db_index=False,
                help_text=BLOCK_HELP,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="served_statuses",
                to="geography.block",
            ),
        ),
        migrations.AddField(
            model_name="servedstatus",
            name="h3_res8",
            field=models.CharField(help_text=H3_HELP, max_length=15, null=True),
        ),
        migrations.RunSQL(FILL_PLACEMENT, reverse_sql=RESTORE_LOCATIONS),
        migrations.AlterField(
            model_name="servedstatus",
            name="block",
            field=models.ForeignKey(
                db_index=False,
                help_text=BLOCK_HELP,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="served_statuses",
                to="geography.block",
            ),
        ),
        migrations.AlterField(
            model_name="servedstatus",
            name="h3_res8",
            field=models.CharField(help_text=H3_HELP, max_length=15),
        ),
        migrations.AlterField(
            model_name="servedstatus",
            name="location_id",
            field=models.BigIntegerField(db_index=True, help_text=LOCATION_ID_HELP),
        ),
        migrations.AddConstraint(
            model_name="servedstatus",
            constraint=models.UniqueConstraint(
                fields=("release", "location_id"),
                name="served_unserved_unique_location_per_release",
            ),
        ),
        migrations.AddConstraint(
            model_name="servedstatus",
            constraint=models.CheckConstraint(
                condition=models.Q(("h3_res8__regex", "^[0-9a-f]{15}$")),
                name="served_unserved_h3_res8_format",
            ),
        ),
        migrations.AddIndex(
            model_name="servedstatus",
            index=models.Index(
                fields=["release", "block"],
                name="servedstatus_release_block",
                opclasses=["int8_ops", "varchar_pattern_ops"],
            ),
        ),
        migrations.AddIndex(
            model_name="servedstatus",
            index=models.Index(fields=["release", "h3_res8"], name="servedstatus_release_h3"),
        ),
        migrations.AlterModelOptions(
            name="servedstatus",
            options={
                "ordering": ["release", "location_id"],
                "verbose_name": "served status",
                "verbose_name_plural": "served statuses",
            },
        ),
    ]
