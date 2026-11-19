"""
Création de la tâche subvention et application SP à la complétion.
"""

import logging

from django.db import transaction
from django.db.models import Count, Q

from productive_inclusion.apps import ProductiveInclusionConfig
from productive_inclusion.models import SereMember, SereSettings, SereSubsidyBatch
from productive_inclusion.status_eligibility import (
    recalculate_all_members_status,
    sync_all_members_to_social_protection,
)

logger = logging.getLogger(__name__)


def _task_source():
    return (
        ProductiveInclusionConfig.sere_subvention_task_source
        or 'subvention_productif'
    )


# Alias pour les signaux / imports existants
TASK_SOURCE = 'subvention_productif'


def _open_subvention_task_exists():
    from tasks_management.models import Task

    sources = {_task_source(), 'productive_inclusion', TASK_SOURCE}
    return Task.objects.filter(
        source__in=sources,
        business_event=ProductiveInclusionConfig.sere_subvention_event,
        status__in=[Task.Status.RECEIVED, Task.Status.ACCEPTED],
        is_deleted=False,
    ).exists()


def create_presence_validation_task(user):
    """
    Recalcule les statuts SERE, crée un SereSubsidyBatch et une tâche subvention.
    Retourne un dict résultat (success, batch, task_id, stats, error).
    """
    from tasks_management.apps import TasksManagementConfig
    from tasks_management.models import Task
    from tasks_management.services import TaskService, _get_std_task_data_payload

    from productive_inclusion.services import _history_save, _resolve_audit_user

    audit_user = _resolve_audit_user(user)
    settings = SereSettings.load()

    if _open_subvention_task_exists():
        return {
            'success': False,
            'error': (
                'Une tâche subvention est déjà en cours (RECEIVED ou ACCEPTED). '
                'Terminez-la avant d\'en créer une nouvelle.'
            ),
        }

    if not settings.benefit_plan_id:
        return {
            'success': False,
            'error': (
                'Aucun régime social protection configuré. '
                'Renseignez le mapping dans Django Admin.'
            ),
        }

    with transaction.atomic():
        stats = recalculate_all_members_status(audit_user, sync_sp=False)

        aggregates = SereMember.objects.filter(is_deleted=False).aggregate(
            total=Count('id'),
            active=Count('id', filter=Q(status=SereMember.Status.ACTIVE)),
            inactive=Count('id', filter=Q(status=SereMember.Status.INACTIVE)),
        )
        active_count = aggregates.get('active') or 0
        inactive_count = aggregates.get('inactive') or 0
        members_total = aggregates.get('total') or 0

        batch = SereSubsidyBatch(
            status=SereSubsidyBatch.Status.PENDING,
            benefit_plan=settings.benefit_plan,
            active_count=active_count,
            inactive_count=inactive_count,
            members_total=members_total,
            summary={
                'presence_count_min': settings.presence_count_min,
                'presence_count_max': settings.presence_count_max,
                'benefit_plan_id': str(settings.benefit_plan_id),
                'benefit_plan_code': getattr(settings.benefit_plan, 'code', None),
                'members_status_updated': stats.get('members_status_updated', 0),
                'sync_social_protection': settings.sync_social_protection,
            },
        )
        _history_save(batch, audit_user)

        benefit_plan_name = getattr(settings.benefit_plan, 'name', None)
        payload = {
            'batch_id': str(batch.id),
            'benefit_plan_id': str(settings.benefit_plan_id),
            'benefit_plan_code': getattr(settings.benefit_plan, 'code', None),
            'benefit_plan_name': benefit_plan_name,
            'benefit_plan_label': (
                f'{getattr(settings.benefit_plan, "code", "")} — {benefit_plan_name}'
                if settings.benefit_plan_id else None
            ),
            'members_total': members_total,
            # Membres SERE ACTIVE → restent / repassent ACTIVE sur le régime SP
            'active_count': active_count,
            'to_keep_active_count': active_count,
            # Membres SERE INACTIVE → SUSPENDED sur le régime SP à la complétion
            'inactive_count': inactive_count,
            'to_suspend_count': inactive_count,
            'presence_count_min': settings.presence_count_min,
            'presence_count_max': settings.presence_count_max,
            'members_status_updated': stats.get('members_status_updated', 0),
            'sync_social_protection': settings.sync_social_protection,
            'label': 'Subvention SERE — validation des présences',
        }

        task_result = TaskService(user).create({
            'source': _task_source(),
            'entity': batch,
            'status': Task.Status.RECEIVED,
            'executor_action_event': TasksManagementConfig.default_executor_event,
            'business_event': ProductiveInclusionConfig.sere_subvention_event,
            'data': _get_std_task_data_payload(payload),
        })

        if not task_result or not task_result.get('success'):
            raise ValueError(
                (task_result or {}).get('message')
                or 'Échec de création de la tâche subvention.'
            )

        task_id = task_result.get('data', {}).get('id') or task_result.get('data', {}).get('uuid')
        if task_id:
            batch.task_id = task_id
            batch.summary = {**batch.summary, 'task_id': str(task_id)}
            _history_save(batch, audit_user)

    return {
        'success': True,
        'batch_id': str(batch.id),
        'task_id': str(task_id) if task_id else None,
        'active_count': active_count,
        'inactive_count': inactive_count,
        'members_total': members_total,
        'members_status_updated': stats.get('members_status_updated', 0),
        'benefit_plan_code': getattr(settings.benefit_plan, 'code', None),
    }


def apply_subvention_batch_on_task_complete(batch, user, failed=False):
    """Applique ou marque en échec le lot après complétion de la tâche."""
    from productive_inclusion.services import _history_save, _resolve_audit_user

    audit_user = _resolve_audit_user(user)
    if failed:
        batch.status = SereSubsidyBatch.Status.FAILED
        _history_save(batch, audit_user)
        return {'success': True, 'applied': False}

    stats = sync_all_members_to_social_protection(audit_user)
    batch.status = SereSubsidyBatch.Status.APPLIED
    batch.summary = {
        **(batch.summary or {}),
        'beneficiaries_suspended': stats.get('beneficiaries_suspended', 0),
        'beneficiaries_reactivated': stats.get('beneficiaries_reactivated', 0),
        'beneficiaries_unmatched': stats.get('beneficiaries_unmatched', 0),
        'warnings': stats.get('warnings', [])[:50],
    }
    _history_save(batch, audit_user)
    return {
        'success': True,
        'applied': True,
        **{k: stats.get(k, 0) for k in (
            'beneficiaries_suspended',
            'beneficiaries_reactivated',
            'beneficiaries_unmatched',
        )},
    }
