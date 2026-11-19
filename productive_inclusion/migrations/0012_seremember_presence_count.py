from django.db import migrations, models
from django.db.models import Count, Q


def backfill_presence_count(apps, schema_editor):
    SereMember = apps.get_model('productive_inclusion', 'SereMember')
    for member in (
        SereMember.objects.filter(is_deleted=False)
        .annotate(
            _pc=Count('presences', filter=Q(presences__is_deleted=False)),
        )
        .iterator(chunk_size=500)
    ):
        count = int(getattr(member, '_pc', 0) or 0)
        if member.presence_count != count:
            SereMember.objects.filter(pk=member.pk).update(presence_count=count)


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('productive_inclusion', '0011_rename_subvention_task_source'),
    ]

    operations = [
        migrations.AddField(
            model_name='seremember',
            name='presence_count',
            field=models.PositiveIntegerField(
                default=0,
                help_text=(
                    'Compteur de présences (import Excel / saisie). '
                    'Utilisé pour le statut SERE selon les seuils admin.'
                ),
                verbose_name='Nombre de présences',
            ),
        ),
        migrations.AddField(
            model_name='historicalseremember',
            name='presence_count',
            field=models.PositiveIntegerField(
                default=0,
                help_text=(
                    'Compteur de présences (import Excel / saisie). '
                    'Utilisé pour le statut SERE selon les seuils admin.'
                ),
                verbose_name='Nombre de présences',
            ),
        ),
        migrations.RunPython(backfill_presence_count, noop_reverse),
    ]
