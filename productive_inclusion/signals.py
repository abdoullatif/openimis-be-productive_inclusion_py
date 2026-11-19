import logging

from core.models import User
from core.service_signals import ServiceSignalBindType
from core.signals import bind_service_signal
from tasks_management.models import Task

from productive_inclusion.apps import ProductiveInclusionConfig
from productive_inclusion.models import SereSubsidyBatch
from productive_inclusion.subsidy_task import _task_source, apply_subvention_batch_on_task_complete

logger = logging.getLogger(__name__)

# Ancienne source (avant renommage en subvention_productif)
_LEGACY_TASK_SOURCES = frozenset({'productive_inclusion'})


def on_task_complete_sere_subvention(**kwargs):
    try:
        result = kwargs.get('result')
        if not result or not result.get('success'):
            return
        task_data = result['data']['task']
        if task_data.get('business_event') != ProductiveInclusionConfig.sere_subvention_event:
            return
        source = task_data.get('source')
        if source != _task_source() and source not in _LEGACY_TASK_SOURCES:
            return

        user = User.objects.get(id=result['data']['user']['id'])
        task_status = task_data.get('status')
        entity_id = task_data.get('entity_id')
        if not entity_id:
            logger.error('Sere subvention task without entity_id: %s', task_data.get('id'))
            return

        batch = SereSubsidyBatch.objects.filter(id=entity_id, is_deleted=False).first()
        if not batch:
            logger.error('SereSubsidyBatch not found for task entity %s', entity_id)
            return

        if batch.status == SereSubsidyBatch.Status.APPLIED:
            return

        if task_status == Task.Status.COMPLETED:
            apply_subvention_batch_on_task_complete(batch, user, failed=False)
        elif task_status == Task.Status.FAILED:
            apply_subvention_batch_on_task_complete(batch, user, failed=True)
    except Exception as exc:
        logger.error('Error while executing on_task_complete_sere_subvention', exc_info=exc)


def bind_service_signals():
    bind_service_signal(
        'task_service.complete_task',
        on_task_complete_sere_subvention,
        bind_type=ServiceSignalBindType.AFTER,
    )
