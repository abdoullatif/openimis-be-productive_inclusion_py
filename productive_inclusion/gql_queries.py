import graphene
from graphene import JSONString
from graphene_django import DjangoObjectType

from core import ExtendedConnection
from productive_inclusion.location_utils import (
    build_location_hierarchy_dict,
    location_labels_for_member_list,
)
from productive_inclusion.models import SereActivity, SereGroup, SereMember


def _member_location_labels(member):
    """Libellés localisation hérités du groupement (même mapping que locationHierarchy)."""
    group = getattr(member, 'group', None)
    if not group or not group.location_id:
        return location_labels_for_member_list(None)
    return location_labels_for_member_list(group.location)


class SereGroupPrefectureCountGQLType(graphene.ObjectType):
    prefecture_name = graphene.String()
    count = graphene.Int()


class SereGroupSummaryGQLType(graphene.ObjectType):
    total_groups = graphene.Int()
    total_members = graphene.Int()
    groups_by_prefecture = graphene.List(SereGroupPrefectureCountGQLType)


class SereGroupGQLType(DjangoObjectType):
    uuid = graphene.String(source='uuid')
    members_count = graphene.Int(
        description='Nombre de membres actifs (non supprimés) du groupement.',
    )
    location_hierarchy = JSONString(
        description='Hiérarchie administrative à partir du village : village, ward, district, region (objets id, uuid, code, name, type).'
    )

    class Meta:
        model = SereGroup
        interfaces = (graphene.relay.Node,)
        filter_fields = {
            'id': ['exact'],
            'import_code': ['exact', 'icontains'],
            'name': ['exact', 'icontains'],
            'locality': ['exact', 'icontains'],
            'location': ['exact'],
            'date_created': ['exact', 'lt', 'lte', 'gt', 'gte'],
            'date_updated': ['exact', 'lt', 'lte', 'gt', 'gte'],
            'is_deleted': ['exact'],
        }
        connection_class = ExtendedConnection

    def resolve_members_count(self, info):
        annotated = getattr(self, 'members_count', None)
        if annotated is not None:
            return annotated
        return self.members.filter(is_deleted=False).count()

    def resolve_location_hierarchy(self, info):
        if not self.location_id:
            return None
        return build_location_hierarchy_dict(self.location)


class SereMemberGQLType(DjangoObjectType):
    uuid = graphene.String(source='uuid')
    sere_group = graphene.Field(
        SereGroupGQLType,
        name='sereGroup',
        description='Groupement SERE du membre (localisation via locationHierarchy).',
    )
    presence_count = graphene.Int(
        description='Nombre de présences enregistrées (non supprimées) pour ce membre.',
    )
    status_display = graphene.String(
        description='Libellé traduit du statut membre.',
    )
    sere_name = graphene.String(description='Nom du groupement SERE.')
    sere_import_code = graphene.String(description='Code import du groupement SERE.')
    prefecture_name = graphene.String(
        description='Préfecture (locationHierarchy.district.name du groupement).',
    )
    sub_prefecture_name = graphene.String(
        description='Sous-préfecture (locationHierarchy.ward.name du groupement).',
    )
    district_name = graphene.String(
        description='District / village (locationHierarchy.village.name du groupement).',
    )

    class Meta:
        model = SereMember
        interfaces = (graphene.relay.Node,)
        filter_fields = {
            'id': ['exact'],
            'last_name': ['exact', 'icontains'],
            'first_name': ['exact', 'icontains'],
            'phone': ['exact', 'icontains'],
            'role': ['exact', 'icontains'],
            'beneficiary_type': ['exact', 'icontains'],
            'code_menage': ['exact', 'icontains'],
            'status': ['exact'],
            'group': ['exact'],
            'date_created': ['exact', 'lt', 'lte', 'gt', 'gte'],
            'date_updated': ['exact', 'lt', 'lte', 'gt', 'gte'],
            'is_deleted': ['exact'],
        }
        connection_class = ExtendedConnection

    @staticmethod
    def resolve_sere_group(member, info):
        if not member.group_id:
            return None
        return member.group

    @staticmethod
    def resolve_presence_count(member, info):
        annotated = getattr(member, 'presence_count', None)
        if annotated is not None:
            return annotated
        return member.presences.filter(is_deleted=False).count()

    @staticmethod
    def resolve_status_display(member, info):
        return member.get_status_display()

    @staticmethod
    def resolve_sere_name(member, info):
        return member.group.name if member.group_id else None

    @staticmethod
    def resolve_sere_import_code(member, info):
        return member.group.import_code if member.group_id else None

    @staticmethod
    def resolve_prefecture_name(member, info):
        return _member_location_labels(member)['prefecture_name']

    @staticmethod
    def resolve_sub_prefecture_name(member, info):
        return _member_location_labels(member)['sub_prefecture_name']

    @staticmethod
    def resolve_district_name(member, info):
        return _member_location_labels(member)['district_name']


class SereActivityGQLType(DjangoObjectType):
    uuid = graphene.String(source='uuid')

    class Meta:
        model = SereActivity
        interfaces = (graphene.relay.Node,)
        filter_fields = {
            'id': ['exact'],
            'title': ['exact', 'icontains'],
            'status': ['exact'],
            'activity_date': ['exact', 'lt', 'lte', 'gt', 'gte'],
            'group': ['exact'],
            'date_created': ['exact', 'lt', 'lte', 'gt', 'gte'],
            'date_updated': ['exact', 'lt', 'lte', 'gt', 'gte'],
            'is_deleted': ['exact'],
        }
        connection_class = ExtendedConnection
