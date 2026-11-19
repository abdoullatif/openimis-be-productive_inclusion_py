from django.db import migrations


OLD_SOURCE = 'productive_inclusion'
NEW_SOURCE = 'subvention_productif'
BUSINESS_EVENT = 'productive_inclusion.subvention'


def rename_task_source(apps, schema_editor):
    Task = apps.get_model('tasks_management', 'Task')
    Task.objects.filter(
        source=OLD_SOURCE,
        business_event=BUSINESS_EVENT,
        is_deleted=False,
    ).update(source=NEW_SOURCE)


def revert_task_source(apps, schema_editor):
    Task = apps.get_model('tasks_management', 'Task')
    Task.objects.filter(
        source=NEW_SOURCE,
        business_event=BUSINESS_EVENT,
        is_deleted=False,
    ).update(source=OLD_SOURCE)


class Migration(migrations.Migration):

    dependencies = [
        ('productive_inclusion', '0010_seresubsidybatch_and_presence_validate_right'),
        ('tasks_management', '0010_add_search_all_perms_admin'),
    ]

    operations = [
        migrations.RunPython(rename_task_source, revert_task_source),
    ]
