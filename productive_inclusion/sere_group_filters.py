"""
Filtres partagés entre sereGroup (liste) et sereGroupSummary (récap).
"""

from django.db.models import Count, Q
from django.db.models.functions import Coalesce
from django.db.models import Value

from core.utils import append_validity_filter
from productive_inclusion.models import SereGroup


def _kw(kwargs, *keys):
    for key in keys:
        if key in kwargs and kwargs[key] is not None and kwargs[key] != '':
            return kwargs[key]
    return None


def apply_sere_group_filters(qs, **kwargs):
    """
    Filtres partagés liste + récap (localisation, texte, dates, nombre de membres).
    Sur sereGroup, django-filter peut aussi appliquer importCode/name/dateUpdated depuis filter_fields.
    """
    import_code = _kw(
        kwargs, 'importCode_Icontains', 'import_code_Icontains', 'importCode_icontains',
    )
    name = _kw(kwargs, 'name_Icontains', 'name_icontains')
    date_updated_gte = _kw(kwargs, 'dateUpdated_Gte', 'date_updated_Gte')
    date_updated_lte = _kw(kwargs, 'dateUpdated_Lte', 'date_updated_Lte')

    if import_code:
        qs = qs.filter(import_code__icontains=import_code)
    if name:
        qs = qs.filter(name__icontains=name)
    if date_updated_gte:
        qs = qs.filter(date_updated__gte=date_updated_gte)
    if date_updated_lte:
        qs = qs.filter(date_updated__lte=date_updated_lte)

    region = _kw(kwargs, 'region_Icontains', 'region_icontains')
    prefecture = _kw(kwargs, 'prefecture_Icontains', 'prefecture_icontains')
    sub_prefecture = _kw(kwargs, 'subPrefecture_Icontains', 'sub_prefecture_icontains')
    district = _kw(kwargs, 'district_Icontains', 'district_icontains')
    members_count = _kw(kwargs, 'membersCount', 'members_count')

    if district:
        qs = qs.filter(
            Q(location__name__icontains=district)
            | Q(location__code__icontains=district)
        )
    if sub_prefecture:
        qs = qs.filter(
            Q(location__parent__name__icontains=sub_prefecture)
            | Q(location__parent__code__icontains=sub_prefecture)
        )
    if prefecture:
        qs = qs.filter(
            Q(location__parent__parent__name__icontains=prefecture)
            | Q(location__parent__parent__code__icontains=prefecture)
        )
    if region:
        qs = qs.filter(
            Q(location__parent__parent__parent__name__icontains=region)
            | Q(location__parent__parent__parent__code__icontains=region)
        )

    qs = qs.annotate(
        members_count=Count('members', filter=Q(members__is_deleted=False)),
    )
    if members_count is not None:
        qs = qs.filter(members_count=int(members_count))

    return qs


def build_sere_group_queryset(user, perms, **kwargs):
    """Queryset de base pour liste / récap, avec droits et filtres custom."""
    if not user.has_perms(perms):
        return SereGroup.objects.none()

    validity_filters = append_validity_filter(**kwargs)
    # Soft-deleted exclus par défaut (ex. après reset SERE).
    qs = SereGroup.objects.filter(*validity_filters, is_deleted=False)
    return apply_sere_group_filters(qs, **kwargs)


def compute_sere_group_summary(qs):
    """
    Agrégations SQL sur les groupements filtrés.
    Le queryset d'entrée peut porter annotate(members_count) (jointure membres) :
    on réagrège sur les seuls ids pour que count = nombre de SERE par préfecture,
    pas la somme des membres.
    """
    from productive_inclusion.models import SereMember

    group_ids = qs.values('id')
    groups_qs = SereGroup.objects.filter(id__in=group_ids)

    total_groups = groups_qs.count()
    total_members = SereMember.objects.filter(
        group_id__in=group_ids,
        is_deleted=False,
    ).count()

    prefecture_rows = (
        groups_qs.annotate(
            prefecture_name=Coalesce('location__parent__parent__name', Value('')),
        )
        .values('prefecture_name')
        .annotate(count=Count('id'))
        .order_by('-count', 'prefecture_name')
    )

    groups_by_prefecture = [
        {
            'prefecture_name': row['prefecture_name'] or '',
            'count': row['count'],
        }
        for row in prefecture_rows
    ]

    return {
        'total_groups': total_groups,
        'total_members': total_members,
        'groups_by_prefecture': groups_by_prefecture,
    }
