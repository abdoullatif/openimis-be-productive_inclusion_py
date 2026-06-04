from django.db import migrations

SERE_IMPORT_RIGHT_ID = 122010


def remove_import_right_assignments(apps, schema_editor):
    RoleRight = apps.get_model('core', 'RoleRight')
    RoleRight.objects.filter(right_id=SERE_IMPORT_RIGHT_ID, validity_to__isnull=True).delete()


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):
    dependencies = [
        ('productive_inclusion', '0002_add_productive_inclusion_rights'),
    ]

    operations = [
        migrations.RunPython(remove_import_right_assignments, noop_reverse),
    ]
