from django import forms
from django.contrib import admin, messages
from django.db.utils import OperationalError, ProgrammingError
from django.utils.translation import gettext_lazy as _

from productive_inclusion.models import (
    SereActivity,
    SereGroup,
    SereMember,
    SereMemberPresence,
    SerePresenceThresholdSettings,
    SereSettings,
    SereSocialProtectionMappingSettings,
    SereSubsidyBatch,
)
from productive_inclusion.status_eligibility import recalculate_all_members_status


def _seresettings_table_ready():
    """False si la migration SereSettings n'est pas encore appliquée."""
    try:
        SereSettings.objects.exists()
        return True
    except (ProgrammingError, OperationalError):
        return False


class _SereSettingsSingletonAdmin(admin.ModelAdmin):
    actions = ['recalculate_statuses']

    def has_module_permission(self, request):
        if not _seresettings_table_ready():
            return False
        return super().has_module_permission(request)

    def has_add_permission(self, request):
        if not _seresettings_table_ready():
            return False
        if SereSettings.objects.exists():
            return False
        return super().has_add_permission(request)

    def has_change_permission(self, request, obj=None):
        if not _seresettings_table_ready():
            return False
        return super().has_change_permission(request, obj)

    def has_view_permission(self, request, obj=None):
        if not _seresettings_table_ready():
            return False
        return super().has_view_permission(request, obj)

    def has_delete_permission(self, request, obj=None):
        return False

    def get_queryset(self, request):
        if _seresettings_table_ready():
            SereSettings.load()
        return super().get_queryset(request)

    @admin.action(description=_('Recalculer tous les statuts SERE (sans sync SP)'))
    def recalculate_statuses(self, request, queryset):
        from productive_inclusion.services import _resolve_audit_user

        stats = recalculate_all_members_status(
            _resolve_audit_user(request.user),
            sync_sp=False,
        )
        self.message_user(
            request,
            _(
                'Recalcul terminé — statuts mis à jour: %(updated)s, inchangés: %(unchanged)s. '
                'La sync régime SP se fait via la tâche subvention.'
            ) % {
                'updated': stats.get('members_status_updated', 0),
                'unchanged': stats.get('members_status_unchanged', 0),
            },
            level=messages.SUCCESS,
        )


@admin.register(SerePresenceThresholdSettings)
class SerePresenceThresholdSettingsAdmin(_SereSettingsSingletonAdmin):
    list_display = ('presence_count_min', 'presence_count_max', 'updated_at')
    fields = ('presence_count_min', 'presence_count_max')

    def get_form(self, request, obj=None, **kwargs):
        form = super().get_form(request, obj, **kwargs)
        form.base_fields['presence_count_min'].help_text = _(
            'ACTIVE si présences ∈ [min, max], sinon INACTIVE. '
            'Exemple : min=8, max=10 → 8 à 10 = ACTIVE ; sinon INACTIVE.'
        )
        return form


@admin.register(SereSocialProtectionMappingSettings)
class SereSocialProtectionMappingSettingsAdmin(_SereSettingsSingletonAdmin):
    list_display = ('benefit_plan', 'sync_social_protection', 'updated_at')
    fields = ('benefit_plan', 'sync_social_protection')

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == 'benefit_plan':
            try:
                from social_protection.models import BenefitPlan

                qs = BenefitPlan.objects.filter(is_deleted=False).order_by('code', 'name')
                kwargs['queryset'] = qs
                field = super().formfield_for_foreignkey(db_field, request, **kwargs)
                field.label_from_instance = lambda obj: f'{obj.code} — {obj.name}'
                field.empty_label = _('---------')
                field.widget = forms.Select()
                field.help_text = _(
                    'Programme de référence. Mapping membres SERE ↔ bénéficiaires via code_ménage '
                    '(individual.json_ext ou group.code). Application à la complétion de la tâche subvention.'
                )
                return field
            except Exception:
                pass
        return super().formfield_for_foreignkey(db_field, request, **kwargs)


@admin.register(SereSubsidyBatch)
class SereSubsidyBatchAdmin(admin.ModelAdmin):
    list_display = (
        'id', 'status', 'benefit_plan', 'active_count', 'inactive_count',
        'members_total', 'task_id', 'date_created',
    )
    list_filter = ('status',)
    readonly_fields = (
        'status', 'benefit_plan', 'active_count', 'inactive_count',
        'members_total', 'summary', 'task_id', 'date_created', 'date_updated',
    )

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(SereGroup)
class SereGroupAdmin(admin.ModelAdmin):
    list_display = ('import_code', 'name', 'locality', 'is_deleted', 'date_updated')
    search_fields = ('import_code', 'name', 'locality')
    list_filter = ('is_deleted',)


@admin.register(SereMember)
class SereMemberAdmin(admin.ModelAdmin):
    list_display = (
        'last_name', 'first_name', 'code_menage', 'presence_count', 'status',
        'group', 'is_deleted',
    )
    search_fields = ('last_name', 'first_name', 'code_menage', 'phone')
    list_filter = ('status', 'is_deleted')
    raw_id_fields = ('group',)
    fields = (
        'group', 'last_name', 'first_name', 'phone', 'role', 'beneficiary_type',
        'code_menage', 'presence_count', 'status',
    )


@admin.register(SereMemberPresence)
class SereMemberPresenceAdmin(admin.ModelAdmin):
    list_display = ('member', 'presence_date', 'is_deleted')
    list_filter = ('is_deleted',)
    raw_id_fields = ('member',)


@admin.register(SereActivity)
class SereActivityAdmin(admin.ModelAdmin):
    list_display = ('title', 'group', 'status', 'activity_date', 'is_deleted')
    list_filter = ('status', 'is_deleted')
    search_fields = ('title',)
    raw_id_fields = ('group',)
