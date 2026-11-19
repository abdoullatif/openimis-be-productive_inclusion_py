import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('productive_inclusion', '0008_reassign_productive_inclusion_right_ids'),
        ('social_protection', '0015_beneficiary_change_log'),
    ]

    operations = [
        migrations.CreateModel(
            name='SereSettings',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('presence_count_min', models.PositiveIntegerField(
                    default=8,
                    help_text='Seuil bas : les membres avec un nombre de présences strictement inférieur passent en statut INACTIVE.',
                    verbose_name='Présences minimum (inclus)',
                )),
                ('presence_count_max', models.PositiveIntegerField(
                    default=10,
                    help_text='Seuil haut : les membres avec un nombre de présences entre min et max (inclus) passent en statut ACTIVE. Au-delà du max → INACTIVE.',
                    verbose_name='Présences maximum (inclus)',
                )),
                ('sync_social_protection', models.BooleanField(
                    default=True,
                    help_text='Si coché : INACTIVE → bénéficiaire SUSPENDED ; ACTIVE → bénéficiaire ACTIVE (hors GRADUATED).',
                    verbose_name='Synchroniser le statut vers social protection',
                )),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('benefit_plan', models.ForeignKey(
                    blank=True,
                    help_text='Programme utilisé pour mapper les membres SERE (via code_ménage) aux bénéficiaires. Les membres INACTIVE seront suspendus sur ce programme (exclus des paiements).',
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='+',
                    to='social_protection.benefitplan',
                    verbose_name='Programme social protection (référence)',
                )),
            ],
            options={
                'verbose_name': 'Paramétrage SERE / subvention',
                'verbose_name_plural': 'Paramétrage SERE / subvention',
            },
        ),
    ]
