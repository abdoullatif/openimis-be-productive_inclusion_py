import graphene
from django.core.exceptions import PermissionDenied, ValidationError
from django.utils.translation import gettext as _

from core.gql.gql_mutations import DeleteInputType, ObjectNotExistException
from core.gql.gql_mutations.base_mutation import (
    BaseDeleteMutation,
    BaseHistoryModelCreateMutationMixin,
    BaseHistoryModelDeleteMutationMixin,
    BaseHistoryModelUpdateMutationMixin,
    BaseMutation,
)
from core.schema import OpenIMISMutation
from productive_inclusion.apps import ProductiveInclusionConfig
from productive_inclusion.gql_queries import SereActivityGQLType
from productive_inclusion.models import SereActivity, SereGroup
from productive_inclusion.services import SereActivityService

ALLOWED_ACTIVITY_STATUSES = {choice.value for choice in SereActivity.Status}


def _normalize_activity_mutation_data(data):
    """GraphQL envoie groupId / activityDate ; le modèle utilise group_id / activity_date."""
    if 'groupId' in data and 'group_id' not in data:
        data['group_id'] = data.pop('groupId')
    elif 'groupId' in data:
        data.pop('groupId', None)
    if 'activityDate' in data and 'activity_date' not in data:
        data['activity_date'] = data.pop('activityDate')
    elif 'activityDate' in data:
        data.pop('activityDate', None)
    return data


def _validate_activity_status(status):
    if status is None:
        return SereActivity.Status.PLANNED
    status = str(status).strip()
    if status not in ALLOWED_ACTIVITY_STATUSES:
        raise ValidationError(
            _('Statut invalide: %(status)s. Valeurs: PLANNED, IN_PROGRESS, COMPLETED, CANCELLED.')
            % {'status': status}
        )
    return status


def _prepare_activity_fields(data, *, require_group=True):
    _normalize_activity_mutation_data(data)
    title = (data.get('title') or '').strip()
    if not title:
        raise ValidationError(_('Le titre de l\'activité est obligatoire.'))

    group_id = data.get('group_id')
    if require_group and not group_id:
        raise ValidationError(_('Le groupement SERE (groupId) est obligatoire.'))

    status = _validate_activity_status(data.get('status'))

    description = data.get('description')
    if description is not None and str(description).strip() == '':
        description = None

    fields = {
        'title': title,
        'description': description,
        'activity_date': data.get('activity_date'),
        'status': status,
    }
    if group_id is not None:
        fields['group_id'] = group_id
    return fields


def _get_active_sere_group(group_id):
    group = SereGroup.objects.filter(id=group_id, is_deleted=False).first()
    if not group:
        raise ValidationError(_('Groupement SERE introuvable.'))
    return group


class CreateSereActivityInput(OpenIMISMutation.Input):
    group_id = graphene.UUID(required=True, name='groupId')
    title = graphene.String(required=True)
    description = graphene.String(required=False)
    activity_date = graphene.Date(required=False, name='activityDate')
    status = graphene.String(required=False)


class UpdateSereActivityInput(CreateSereActivityInput):
    id = graphene.UUID(required=True)


class CreateSereActivityMutation(BaseHistoryModelCreateMutationMixin, BaseMutation):
    _mutation_class = 'CreateSereActivityMutation'
    _mutation_module = 'productive_inclusion'
    _model = SereActivity

    sere_activity = graphene.Field(SereActivityGQLType)

    class Input(CreateSereActivityInput):
        pass

    @classmethod
    def _validate_mutation(cls, user, **data):
        super()._validate_mutation(user, **data)
        if not user.has_perms(ProductiveInclusionConfig.gql_sere_activity_create_perms):
            raise PermissionDenied(_('unauthorized'))
        fields = _prepare_activity_fields(data, require_group=True)
        _get_active_sere_group(fields['group_id'])

    @classmethod
    def _mutate(cls, user, **data):
        data.pop('client_mutation_id', None)
        data.pop('client_mutation_label', None)
        fields = _prepare_activity_fields(data, require_group=True)
        activity = SereActivityService.create(user, fields)
        cls._last_activity = activity
        return None

    @classmethod
    def create_object(cls, user, object_data):
        fields = _prepare_activity_fields(object_data, require_group=True)
        return SereActivityService.create(user, fields)


class UpdateSereActivityMutation(BaseHistoryModelUpdateMutationMixin, BaseMutation):
    _mutation_class = 'UpdateSereActivityMutation'
    _mutation_module = 'productive_inclusion'
    _model = SereActivity

    sere_activity = graphene.Field(SereActivityGQLType)

    class Input(UpdateSereActivityInput):
        pass

    @classmethod
    def _validate_mutation(cls, user, **data):
        super()._validate_mutation(user, **data)
        if not user.has_perms(ProductiveInclusionConfig.gql_sere_activity_update_perms):
            raise PermissionDenied(_('unauthorized'))

        _normalize_activity_mutation_data(data)
        activity_id = data.get('id')
        activity = SereActivity.objects.filter(id=activity_id, is_deleted=False).first()
        if not activity:
            cls._object_not_exist_exception(activity_id)

        group_id = data.get('group_id')
        if group_id and activity.group_id != group_id:
            raise ValidationError(_('L\'activité n\'appartient pas à ce groupement SERE.'))

        _prepare_activity_fields(data, require_group=False)

    @classmethod
    def _mutate(cls, user, **data):
        data.pop('client_mutation_id', None)
        data.pop('client_mutation_label', None)
        _normalize_activity_mutation_data(data)

        activity_id = data.pop('id')
        group_id = data.pop('group_id', None)

        activity = SereActivity.objects.filter(id=activity_id, is_deleted=False).first()
        if not activity:
            cls._object_not_exist_exception(activity_id)
        if group_id and activity.group_id != group_id:
            raise ValidationError(_('L\'activité n\'appartient pas à ce groupement SERE.'))

        fields = _prepare_activity_fields(data, require_group=False)
        activity = SereActivityService.update(user, activity, fields)
        cls._last_activity = activity
        return None

    @classmethod
    def update_object(cls, user, object_to_update):
        return SereActivityService.update(user, object_to_update, {})


class DeleteSereActivityMutation(BaseHistoryModelDeleteMutationMixin, BaseDeleteMutation):
    _mutation_class = 'DeleteSereActivityMutation'
    _mutation_module = 'productive_inclusion'
    _model = SereActivity

    class Input(DeleteInputType):
        pass

    @classmethod
    def _validate_mutation(cls, user, **data):
        super()._validate_mutation(user, **data)
        if not user.has_perms(ProductiveInclusionConfig.gql_sere_activity_delete_perms):
            raise PermissionDenied(_('unauthorized'))

    @classmethod
    def __delete_single_obj(cls, user, id_):
        activity = cls._model.objects.filter(id=id_, is_deleted=False).first()
        if activity is None:
            cls._object_not_exist_exception(id_)
        SereActivityService.delete(user, activity)
