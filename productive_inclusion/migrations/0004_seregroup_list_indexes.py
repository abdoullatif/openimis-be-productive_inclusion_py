from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('productive_inclusion', '0003_remove_sere_import_role_rights'),
    ]

    operations = [
        migrations.AddIndex(
            model_name='seregroup',
            index=models.Index(fields=['import_code'], name='pi_seregroup_import_code_idx'),
        ),
        migrations.AddIndex(
            model_name='seregroup',
            index=models.Index(fields=['name'], name='pi_seregroup_name_idx'),
        ),
        migrations.AddIndex(
            model_name='seregroup',
            index=models.Index(fields=['date_updated'], name='pi_seregroup_date_upd_idx'),
        ),
        migrations.AddIndex(
            model_name='seregroup',
            index=models.Index(fields=['location'], name='pi_seregroup_location_idx'),
        ),
    ]
