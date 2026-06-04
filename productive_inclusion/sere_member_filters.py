"""
Filtres liste globale des membres SERE (sous-menu Membres).
"""

from django.db.models import Count, Prefetch, Q

from core.utils import append_validity_filter
from productive_inclusion.models import SereGroup, SereMember


def _prefetch_sere_group_with_location():
    """Prefetch (pas select_related) : compatible avec gql_optimizer.defer sur group."""
    return Prefetch(
        'group',
        queryset=SereGroup.objects.select_related(
            'location',
            'location__parent',
            'location__parent__parent',
            'location__parent__parent__parent',
        ),
    )


def _kw(kwargs, *keys):
    for key in keys:
        if key in kwargs and kwargs[key] is not None and kwargs[key] != '':
            return kwargs[key]
    return None


def apply_sere_member_filters(qs, **kwargs):
    code_menage = _kw(kwargs, 'codeMenage_Icontains', 'code_menage_Icontains')
    last_name = _kw(kwargs, 'lastName_Icontains', 'last_name_Icontains')
    first_name = _kw(kwargs, 'firstName_Icontains', 'first_name_Icontains')
    phone = _kw(kwargs, 'phone_Icontains')
    role = _kw(kwargs, 'role_Icontains')
    beneficiary_type = _kw(
        kwargs, 'beneficiaryType_Icontains', 'beneficiary_type_Icontains',
    )
    sere_name = _kw(kwargs, 'sereName_Icontains', 'sere_name_Icontains')
    sere_import_code = _kw(
        kwargs, 'sereImportCode_Icontains', 'sere_import_code_Icontains',
    )
    status = _kw(kwargs, 'status', 'status_Exact', 'status_exact')
    presence_count = _kw(kwargs, 'presenceCount', 'presence_count')
    group_id = _kw(kwargs, 'groupId', 'group_id')

    prefecture = _kw(kwargs, 'prefecture_Icontains', 'prefecture_icontains')
    sub_prefecture = _kw(kwargs, 'subPrefecture_Icontains', 'sub_prefecture_icontains')
    district = _kw(kwargs, 'district_Icontains', 'district_icontains')

    if code_menage:
        qs = qs.filter(code_menage__icontains=code_menage)
    if last_name:
        qs = qs.filter(last_name__icontains=last_name)
    if first_name:
        qs = qs.filter(first_name__icontains=first_name)
    if phone:
        qs = qs.filter(phone__icontains=phone)
    if role:
        qs = qs.filter(role__icontains=role)
    if beneficiary_type:
        qs = qs.filter(beneficiary_type__icontains=beneficiary_type)
    if sere_name:
        qs = qs.filter(group__name__icontains=sere_name)
    if sere_import_code:
        qs = qs.filter(group__import_code__icontains=sere_import_code)
    if status:
        qs = qs.filter(status=status)
    if group_id:
        qs = qs.filter(group_id=group_id)

    # Filtres localité via le groupement (équivalent locationHierarchy : village / ward / district)
    if district:
        qs = qs.filter(
            Q(group__location__name__icontains=district)
            | Q(group__location__code__icontains=district)
        )
    if sub_prefecture:
        qs = qs.filter(
            Q(group__location__parent__name__icontains=sub_prefecture)
            | Q(group__location__parent__code__icontains=sub_prefecture)
        )
    if prefecture:
        qs = qs.filter(
            Q(group__location__parent__parent__name__icontains=prefecture)
            | Q(group__location__parent__parent__code__icontains=prefecture)
        )

    if presence_count is not None:
        qs = qs.filter(presence_count=int(presence_count))

    return qs


def _annotate_member_list(qs):
    return qs.annotate(
        presence_count=Count(
            'presences',
            filter=Q(presences__is_deleted=False),
        ),
    )


def _apply_group_location_select_related(qs):
    """Liste globale Membres : jointures pour localités + sereGroup.locationHierarchy."""
    return qs.select_related(
        'group',
        'group__location',
        'group__location__parent',
        'group__location__parent__parent',
        'group__location__parent__parent__parent',
    )


def build_sere_member_list_queryset(user, perms, **kwargs):
    """Sous-menu Membres (sans groupId) — ne pas utiliser sur la fiche détail SERE."""
    if not user.has_perms(perms):
        return SereMember.objects.none()

    validity_filters = append_validity_filter(**kwargs)
    qs = _annotate_member_list(SereMember.objects.filter(*validity_filters))
    qs = _apply_group_location_select_related(qs)
    return apply_sere_member_filters(qs, **kwargs)


def build_sere_member_by_group_queryset(user, perms, **kwargs):
    """
    Fiche détail SERE (groupId) — prefetch uniquement : évite le conflit
    defer(group) + select_related avec gql_optimizer.
    """
    if not user.has_perms(perms):
        return SereMember.objects.none()

    validity_filters = append_validity_filter(**kwargs)
    qs = _annotate_member_list(SereMember.objects.filter(*validity_filters))
    qs = qs.prefetch_related(_prefetch_sere_group_with_location())
    return apply_sere_member_filters(qs, **kwargs)


def build_sere_member_queryset(user, perms, **kwargs):
    group_id = _kw(kwargs, 'groupId', 'group_id')
    if group_id:
        return build_sere_member_by_group_queryset(user, perms, **kwargs)
    return build_sere_member_list_queryset(user, perms, **kwargs)
