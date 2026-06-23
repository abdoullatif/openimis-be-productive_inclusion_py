"""
Les droits 122001-122006 appartiennent au module core (gestion des rôles).
productive_inclusion utilisait par erreur la même plage → collision.
Nouvelle plage dédiée : 124001-124009.
"""

import json

from django.db import migrations

IMIS_ADMINISTRATOR_SYSTEM = 64

OLD_RIGHTS = list(range(122001, 122010))
NEW_RIGHTS = list(range(124001, 124010))
OLD_TO_NEW = dict(zip(OLD_RIGHTS, NEW_RIGHTS))
PI_EXCLUSIVE_OLD = {122007, 122008, 122009}
PI_GROUP_OLD = set(range(122001, 122007))


def _add_right_for_role(role, right_id, RoleRight):
    if RoleRight.objects.filter(
        role=role, right_id=right_id, validity_to__isnull=True,
    ).exists():
        return
    RoleRight.objects.create(role=role, right_id=right_id, audit_user_id=1)


def _update_module_configuration(apps):
    ModuleConfiguration = apps.get_model('core', 'ModuleConfiguration')
    for mc in ModuleConfiguration.objects.filter(module='productive_inclusion', layer='be'):
        try:
            config = json.loads(mc.config or '{}')
        except json.JSONDecodeError:
            continue
        changed = False
        for key, value in list(config.items()):
            if not isinstance(value, list):
                continue
            new_list = []
            for item in value:
                try:
                    right_id = int(item)
                except (TypeError, ValueError):
                    new_list.append(item)
                    continue
                if right_id in OLD_TO_NEW:
                    new_list.append(str(OLD_TO_NEW[right_id]))
                    changed = True
                else:
                    new_list.append(item)
            config[key] = new_list
        if changed:
            mc.config = json.dumps(config)
            mc.save(update_fields=['config'])


def reassign_rights(apps, schema_editor):
    RoleRight = apps.get_model('core', 'RoleRight')
    Role = apps.get_model('core', 'Role')

    _update_module_configuration(apps)

    admin_role = Role.objects.filter(is_system=IMIS_ADMINISTRATOR_SYSTEM).first()
    if admin_role:
        for new_id in NEW_RIGHTS:
            _add_right_for_role(admin_role, new_id, RoleRight)

    for old_id in PI_EXCLUSIVE_OLD:
        new_id = OLD_TO_NEW[old_id]
        for rr in RoleRight.objects.filter(right_id=old_id, validity_to__isnull=True):
            _add_right_for_role(rr.role, new_id, RoleRight)
            rr.delete()

    roles_with_pi = set(
        RoleRight.objects.filter(
            right_id__in=[OLD_TO_NEW[x] for x in PI_EXCLUSIVE_OLD],
            validity_to__isnull=True,
        ).values_list('role_id', flat=True)
    )

    for role_id in roles_with_pi:
        role = Role.objects.filter(pk=role_id).first()
        if not role:
            continue
        for old_id in PI_GROUP_OLD:
            if RoleRight.objects.filter(
                role=role, right_id=old_id, validity_to__isnull=True,
            ).exists():
                _add_right_for_role(role, OLD_TO_NEW[old_id], RoleRight)


def reverse_reassign(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('productive_inclusion', '0007_sere_member_status_and_presence'),
    ]

    operations = [
        migrations.RunPython(reassign_rights, reverse_reassign),
    ]
