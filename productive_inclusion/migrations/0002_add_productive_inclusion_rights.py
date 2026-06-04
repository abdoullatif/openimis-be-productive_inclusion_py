from django.db import migrations

PRODUCTIVE_INCLUSION_RIGHTS = [
    122001,
    122002,
    122003,
    122004,
    122005,
    122006,
    122007,
    122008,
    122009,
]
IMIS_ADMINISTRATOR_SYSTEM = 64


def _add_right_for_role(role, right_id, RoleRight):
    RoleRight.objects.create(role=role, right_id=right_id, audit_user_id=1)


def add_rights(role_id, apps):
    RoleRight = apps.get_model('core', 'RoleRight')
    Role = apps.get_model('core', 'Role')
    role = Role.objects.get(is_system=role_id)
    for right_id in PRODUCTIVE_INCLUSION_RIGHTS:
        if not RoleRight.objects.filter(validity_to__isnull=True, role=role, right_id=right_id).exists():
            _add_right_for_role(role, right_id, RoleRight)


def remove_rights(role_id, apps):
    RoleRight = apps.get_model('core', 'RoleRight')
    RoleRight.objects.filter(
        role__is_system=role_id,
        right_id__in=PRODUCTIVE_INCLUSION_RIGHTS,
        validity_to__isnull=True,
    ).delete()


def on_migration(apps, schema_editor):
    add_rights(IMIS_ADMINISTRATOR_SYSTEM, apps)


def on_reverse_migration(apps, schema_editor):
    remove_rights(IMIS_ADMINISTRATOR_SYSTEM, apps)


class Migration(migrations.Migration):
    dependencies = [
        ('productive_inclusion', '0001_initial'),
    ]

    operations = [
        migrations.RunPython(on_migration, on_reverse_migration),
    ]
