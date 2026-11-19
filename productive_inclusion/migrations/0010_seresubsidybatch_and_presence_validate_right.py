import datetime

import dirtyfields.dirtyfields
import django.db.models.deletion
import simple_history.models
from django.conf import settings
from django.db import migrations, models

import core.fields


IMIS_ADMINISTRATOR_SYSTEM = 64
RIGHT_PRESENCE_VALIDATE = 124010


def add_presence_validate_right(apps, schema_editor):
    Role = apps.get_model('core', 'Role')
    RoleRight = apps.get_model('core', 'RoleRight')
    admin_role = Role.objects.filter(is_system=IMIS_ADMINISTRATOR_SYSTEM).first()
    if not admin_role:
        return
    if RoleRight.objects.filter(
        role=admin_role, right_id=RIGHT_PRESENCE_VALIDATE, validity_to__isnull=True,
    ).exists():
        return
    RoleRight.objects.create(
        role=admin_role, right_id=RIGHT_PRESENCE_VALIDATE, audit_user_id=1,
    )


def remove_presence_validate_right(apps, schema_editor):
    RoleRight = apps.get_model('core', 'RoleRight')
    RoleRight.objects.filter(
        right_id=RIGHT_PRESENCE_VALIDATE, validity_to__isnull=True,
    ).delete()


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('social_protection', '0015_beneficiary_change_log'),
        ('productive_inclusion', '0009_seresettings'),
    ]

    operations = [
        migrations.CreateModel(
            name='SereSubsidyBatch',
            fields=[
                ('id', models.UUIDField(db_column='UUID', default=None, editable=False, primary_key=True, serialize=False)),
                ('is_deleted', models.BooleanField(db_column='isDeleted', default=False)),
                ('json_ext', models.JSONField(blank=True, db_column='Json_ext', null=True)),
                ('date_created', core.fields.DateTimeField(db_column='DateCreated', default=datetime.datetime.now, null=True)),
                ('date_updated', core.fields.DateTimeField(db_column='DateUpdated', default=datetime.datetime.now, null=True)),
                ('version', models.IntegerField(default=1)),
                ('status', models.CharField(
                    choices=[('PENDING', 'En attente'), ('APPLIED', 'Appliqué'), ('FAILED', 'Échoué')],
                    default='PENDING',
                    max_length=32,
                )),
                ('active_count', models.PositiveIntegerField(default=0)),
                ('inactive_count', models.PositiveIntegerField(default=0)),
                ('members_total', models.PositiveIntegerField(default=0)),
                ('summary', models.JSONField(blank=True, default=dict)),
                ('task_id', models.UUIDField(blank=True, null=True)),
                ('benefit_plan', models.ForeignKey(
                    blank=True,
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='+',
                    to='social_protection.benefitplan',
                )),
                ('user_created', models.ForeignKey(
                    db_column='UserCreatedUUID',
                    on_delete=django.db.models.deletion.DO_NOTHING,
                    related_name='%(class)s_user_created',
                    to=settings.AUTH_USER_MODEL,
                )),
                ('user_updated', models.ForeignKey(
                    db_column='UserUpdatedUUID',
                    on_delete=django.db.models.deletion.DO_NOTHING,
                    related_name='%(class)s_user_updated',
                    to=settings.AUTH_USER_MODEL,
                )),
            ],
            options={
                'verbose_name': 'Lot validation subvention SERE',
                'verbose_name_plural': 'Lots validation subvention SERE',
                'ordering': ('-date_created',),
            },
            bases=(dirtyfields.dirtyfields.DirtyFieldsMixin, models.Model),
        ),
        migrations.CreateModel(
            name='HistoricalSereSubsidyBatch',
            fields=[
                ('id', models.UUIDField(db_column='UUID', db_index=True, default=None, editable=False)),
                ('is_deleted', models.BooleanField(db_column='isDeleted', default=False)),
                ('json_ext', models.JSONField(blank=True, db_column='Json_ext', null=True)),
                ('date_created', core.fields.DateTimeField(db_column='DateCreated', default=datetime.datetime.now, null=True)),
                ('date_updated', core.fields.DateTimeField(db_column='DateUpdated', default=datetime.datetime.now, null=True)),
                ('version', models.IntegerField(default=1)),
                ('status', models.CharField(
                    choices=[('PENDING', 'En attente'), ('APPLIED', 'Appliqué'), ('FAILED', 'Échoué')],
                    default='PENDING',
                    max_length=32,
                )),
                ('active_count', models.PositiveIntegerField(default=0)),
                ('inactive_count', models.PositiveIntegerField(default=0)),
                ('members_total', models.PositiveIntegerField(default=0)),
                ('summary', models.JSONField(blank=True, default=dict)),
                ('task_id', models.UUIDField(blank=True, null=True)),
                ('history_id', models.AutoField(primary_key=True, serialize=False)),
                ('history_date', models.DateTimeField(db_index=True)),
                ('history_change_reason', models.CharField(max_length=100, null=True)),
                ('history_type', models.CharField(choices=[('+', 'Created'), ('~', 'Changed'), ('-', 'Deleted')], max_length=1)),
                ('benefit_plan', models.ForeignKey(
                    blank=True, db_constraint=False, null=True,
                    on_delete=django.db.models.deletion.DO_NOTHING, related_name='+',
                    to='social_protection.benefitplan',
                )),
                ('history_user', models.ForeignKey(
                    null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+',
                    to=settings.AUTH_USER_MODEL,
                )),
                ('user_created', models.ForeignKey(
                    blank=True, db_column='UserCreatedUUID', db_constraint=False, null=True,
                    on_delete=django.db.models.deletion.DO_NOTHING, related_name='+',
                    to=settings.AUTH_USER_MODEL,
                )),
                ('user_updated', models.ForeignKey(
                    blank=True, db_column='UserUpdatedUUID', db_constraint=False, null=True,
                    on_delete=django.db.models.deletion.DO_NOTHING, related_name='+',
                    to=settings.AUTH_USER_MODEL,
                )),
            ],
            options={
                'verbose_name': 'historical Lot validation subvention SERE',
                'verbose_name_plural': 'historical Lots validation subvention SERE',
                'ordering': ('-history_date', '-history_id'),
                'get_latest_by': ('history_date', 'history_id'),
            },
            bases=(simple_history.models.HistoricalChanges, models.Model),
        ),
        migrations.CreateModel(
            name='SerePresenceThresholdSettings',
            fields=[],
            options={
                'verbose_name': 'Seuils de présence SERE',
                'verbose_name_plural': 'Seuils de présence SERE',
                'proxy': True,
                'indexes': [],
                'constraints': [],
            },
            bases=('productive_inclusion.seresettings',),
        ),
        migrations.CreateModel(
            name='SereSocialProtectionMappingSettings',
            fields=[],
            options={
                'verbose_name': 'Mapping régime social protection',
                'verbose_name_plural': 'Mapping régime social protection',
                'proxy': True,
                'indexes': [],
                'constraints': [],
            },
            bases=('productive_inclusion.seresettings',),
        ),
        migrations.RunPython(add_presence_validate_right, remove_presence_validate_right),
    ]
