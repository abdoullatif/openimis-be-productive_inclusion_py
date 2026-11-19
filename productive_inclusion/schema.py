import graphene
import graphene_django_optimizer as gql_optimizer
from django.core.exceptions import PermissionDenied
from django.db.models import Q
from django.utils.translation import gettext as _

from core.schema import OrderedDjangoFilterConnectionField
from core.services import wait_for_mutation
from productive_inclusion.apps import ProductiveInclusionConfig
from productive_inclusion.gql_mutations import (
    CreateSereActivityMutation,
    DeleteSereActivityMutation,
    UpdateSereActivityMutation,
)
from productive_inclusion.gql_queries import (
    SereActivityGQLType,
    SereGroupGQLType,
    SereGroupSummaryGQLType,
    SereMemberGQLType,
)
from productive_inclusion.models import SereActivity, SereMember
from productive_inclusion.sere_group_filters import (
    build_sere_group_queryset,
    compute_sere_group_summary,
)
from productive_inclusion.sere_member_filters import build_sere_member_queryset

def _sere_filter_string(graphql_name):
    """Noms d'arguments alignés openIMIS (ex. name_Icontains, importCode_Icontains)."""
    return graphene.Argument(graphene.String, name=graphql_name)


def _sere_filter_datetime(graphql_name):
    return graphene.Argument(graphene.DateTime, name=graphql_name)


SERE_MEMBER_LIST_FILTER_ARGS = {
    'codeMenage_Icontains': _sere_filter_string('codeMenage_Icontains'),
    'lastName_Icontains': _sere_filter_string('lastName_Icontains'),
    'firstName_Icontains': _sere_filter_string('firstName_Icontains'),
    'phone_Icontains': _sere_filter_string('phone_Icontains'),
    'role_Icontains': _sere_filter_string('role_Icontains'),
    'beneficiaryType_Icontains': _sere_filter_string('beneficiaryType_Icontains'),
    'sereName_Icontains': _sere_filter_string('sereName_Icontains'),
    'sereImportCode_Icontains': _sere_filter_string('sereImportCode_Icontains'),
    'prefecture_Icontains': _sere_filter_string('prefecture_Icontains'),
    'subPrefecture_Icontains': _sere_filter_string('subPrefecture_Icontains'),
    'district_Icontains': _sere_filter_string('district_Icontains'),
    'presenceCount': graphene.Argument(graphene.Int, name='presenceCount'),
}


SERE_GROUP_LIST_FILTER_ARGS = {
    'importCode_Icontains': _sere_filter_string('importCode_Icontains'),
    'name_Icontains': _sere_filter_string('name_Icontains'),
    'dateUpdated_Gte': _sere_filter_datetime('dateUpdated_Gte'),
    'dateUpdated_Lte': _sere_filter_datetime('dateUpdated_Lte'),
    'region_Icontains': _sere_filter_string('region_Icontains'),
    'prefecture_Icontains': _sere_filter_string('prefecture_Icontains'),
    'subPrefecture_Icontains': _sere_filter_string('subPrefecture_Icontains'),
    'district_Icontains': _sere_filter_string('district_Icontains'),
    'membersCount': graphene.Argument(graphene.Int, name='membersCount'),
}


class Query(graphene.ObjectType):
    module_name = 'productive_inclusion'

    sere_group = OrderedDjangoFilterConnectionField(
        SereGroupGQLType,
        orderBy=graphene.List(of_type=graphene.String),
        dateValidFrom__Gte=graphene.DateTime(),
        dateValidTo__Lte=graphene.DateTime(),
        client_mutation_id=graphene.String(),
        **SERE_GROUP_LIST_FILTER_ARGS,
    )
    sere_group_summary = graphene.Field(
        SereGroupSummaryGQLType,
        dateValidFrom__Gte=graphene.DateTime(),
        dateValidTo__Lte=graphene.DateTime(),
        **SERE_GROUP_LIST_FILTER_ARGS,
    )
    sere_member = OrderedDjangoFilterConnectionField(
        SereMemberGQLType,
        orderBy=graphene.List(of_type=graphene.String),
        dateValidFrom__Gte=graphene.DateTime(),
        dateValidTo__Lte=graphene.DateTime(),
        client_mutation_id=graphene.String(),
        groupId=graphene.UUID(),
        **SERE_MEMBER_LIST_FILTER_ARGS,
    )
    sere_activity = OrderedDjangoFilterConnectionField(
        SereActivityGQLType,
        orderBy=graphene.List(of_type=graphene.String),
        dateValidFrom__Gte=graphene.DateTime(),
        dateValidTo__Lte=graphene.DateTime(),
        client_mutation_id=graphene.String(),
        groupId=graphene.UUID(),
    )

    def resolve_sere_group(self, info, **kwargs):
        client_mutation_id = kwargs.get('client_mutation_id')
        if client_mutation_id:
            wait_for_mutation(client_mutation_id)

        qs = build_sere_group_queryset(
            info.context.user,
            ProductiveInclusionConfig.gql_sere_group_search_perms,
            **kwargs,
        )
        return gql_optimizer.query(qs, info)

    def resolve_sere_group_summary(self, info, **kwargs):
        if not info.context.user.has_perms(ProductiveInclusionConfig.gql_sere_group_search_perms):
            raise PermissionDenied(_('unauthorized'))

        qs = build_sere_group_queryset(
            info.context.user,
            ProductiveInclusionConfig.gql_sere_group_search_perms,
            **kwargs,
        )
        data = compute_sere_group_summary(qs)
        return SereGroupSummaryGQLType(
            total_groups=data['total_groups'],
            total_members=data['total_members'],
            groups_by_prefecture=[
                {'prefecture_name': row['prefecture_name'], 'count': row['count']}
                for row in data['groups_by_prefecture']
            ],
        )

    def resolve_sere_member(self, info, **kwargs):
        client_mutation_id = kwargs.get('client_mutation_id')
        if client_mutation_id:
            wait_for_mutation(client_mutation_id)
        qs = build_sere_member_queryset(
            info.context.user,
            ProductiveInclusionConfig.gql_sere_member_search_perms,
            **kwargs,
        )
        return gql_optimizer.query(qs, info)

    def resolve_sere_activity(self, info, **kwargs):
        from core.utils import append_validity_filter

        filters = append_validity_filter(**kwargs)
        client_mutation_id = kwargs.get('client_mutation_id')
        if client_mutation_id:
            wait_for_mutation(client_mutation_id)
        group_id = kwargs.get('groupId')
        if group_id:
            filters.append(Q(group_id=group_id))
        if not info.context.user.has_perms(ProductiveInclusionConfig.gql_sere_activity_search_perms):
            return SereActivity.objects.none()
        filters.append(Q(is_deleted=False))
        return gql_optimizer.query(SereActivity.objects.filter(*filters), info)


class Mutation(graphene.ObjectType):
    create_sere_activity = CreateSereActivityMutation.Field()
    update_sere_activity = UpdateSereActivityMutation.Field()
    delete_sere_activity = DeleteSereActivityMutation.Field()
