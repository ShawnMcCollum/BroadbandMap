"""Give every rollup row the state whose statuses it counts (ADR 0017).

Written by hand: the generated migration would need a default for the new column. This one fills
it from the data. A census code starts with its state's FIPS code, and an H3 cell's state is that
of its statuses in the release. Undoing it fails once a release holds two states' rows for one H3
cell, since the restored unique constraint has no state.
"""

import django.db.models.deletion
import django.db.models.functions.text
import django.db.models.lookups
from django.db import migrations, models

FILL_STATE = """
UPDATE served_unserved_rollup AS r
SET state_id = CASE
    WHEN r.level = 'h3_res8' THEN (
        SELECT left(s.block_id, 2)
        FROM served_unserved_servedstatus AS s
        WHERE s.release_id = r.release_id AND s.h3_res8 = r.code
        LIMIT 1
    )
    ELSE left(r.code, 2)
END
"""

STATE_HELP = (
    "State whose statuses the row counts. A census area's code starts with the state's "
    "FIPS code; an H3 cell on a state line has one row per state."
)


class Migration(migrations.Migration):
    dependencies = [
        ("geography", "0002_block_place_county_subdivision"),
        ("served_unserved", "0005_placement_per_release"),
    ]

    operations = [
        # Before the fill, so that it does not update the index row by row. It is rebuilt with
        # the state below.
        migrations.RemoveConstraint(
            model_name="rollup",
            name="served_unserved_rollup_unique_area_per_release",
        ),
        # Nullable, and without a foreign key constraint, until filled
        migrations.AddField(
            model_name="rollup",
            name="state",
            field=models.ForeignKey(
                db_constraint=False,
                db_index=False,
                help_text=STATE_HELP,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="rollups",
                to="geography.state",
            ),
        ),
        migrations.RunSQL(FILL_STATE, reverse_sql=migrations.RunSQL.noop),
        migrations.AlterField(
            model_name="rollup",
            name="state",
            field=models.ForeignKey(
                db_index=False,
                help_text=STATE_HELP,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="rollups",
                to="geography.state",
            ),
        ),
        migrations.AlterModelOptions(
            name="rollup",
            options={
                "ordering": ["release", "level", "code", "state"],
                "verbose_name": "rollup",
                "verbose_name_plural": "rollups",
            },
        ),
        migrations.AddConstraint(
            model_name="rollup",
            constraint=models.UniqueConstraint(
                fields=("release", "level", "code", "state"),
                name="served_unserved_rollup_unique_area_per_state",
            ),
        ),
        migrations.AddConstraint(
            model_name="rollup",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    ("level", "h3_res8"),
                    django.db.models.lookups.Exact(
                        django.db.models.functions.text.Left("code", 2), models.F("state")
                    ),
                    _connector="OR",
                ),
                name="served_unserved_rollup_code_in_state",
            ),
        ),
        migrations.AddIndex(
            model_name="rollup",
            index=models.Index(
                fields=["release", "state", "level"], name="rollup_release_state_level"
            ),
        ),
    ]
