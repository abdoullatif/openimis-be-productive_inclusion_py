"""
Éligibilité SERE : statut dynamique selon le nombre de présences,
et synchronisation vers les bénéficiaires du programme social protection.
"""

import logging

from productive_inclusion.models import SereMember, SereSettings

logger = logging.getLogger(__name__)


def _ensure_stats(stats):
    if stats is None:
        return {
            'members_status_updated': 0,
            'members_status_unchanged': 0,
            'beneficiaries_suspended': 0,
            'beneficiaries_reactivated': 0,
            'beneficiaries_unmatched': 0,
            'warnings': [],
        }
    for key in (
        'members_status_updated',
        'members_status_unchanged',
        'beneficiaries_suspended',
        'beneficiaries_reactivated',
        'beneficiaries_unmatched',
    ):
        stats.setdefault(key, 0)
    stats.setdefault('warnings', [])
    return stats


def presence_count_for_member(member):
    """Source de vérité : SereMember.presence_count."""
    return int(getattr(member, 'presence_count', 0) or 0)


def status_from_presence_count(count, settings=None):
    """
    ACTIVE si min <= count <= max, sinon INACTIVE.
    """
    settings = settings or SereSettings.load()
    minimum = int(settings.presence_count_min)
    maximum = int(settings.presence_count_max)
    if minimum <= int(count) <= maximum:
        return SereMember.Status.ACTIVE
    return SereMember.Status.INACTIVE


def _history_save_member(member, audit_user):
    from productive_inclusion.services import _history_save

    _history_save(member, audit_user)


def _find_sp_beneficiaries(benefit_plan, code_menage):
    """
    Correspondance par code_ménage :
    - Beneficiary (programme INDIVIDUAL) via individual.json_ext / beneficiary.json_ext
    - GroupBeneficiary (programme GROUP) via group.code
    """
    from django.db.models.fields.json import KeyTextTransform

    from social_protection.models import (
        Beneficiary,
        BenefitPlan,
        GroupBeneficiary,
    )

    code = str(code_menage).strip()
    results = []

    if benefit_plan.type == BenefitPlan.BenefitPlanType.INDIVIDUAL_TYPE:
        qs = Beneficiary.objects.filter(
            benefit_plan=benefit_plan,
            is_deleted=False,
        ).annotate(
            ind_code_menage=KeyTextTransform('code_menage', 'individual__json_ext'),
            ind_code_menage_camel=KeyTextTransform('codeMenage', 'individual__json_ext'),
            ben_code_menage=KeyTextTransform('code_menage', 'json_ext'),
            ben_code_menage_camel=KeyTextTransform('codeMenage', 'json_ext'),
        ).filter(
            Q(ind_code_menage=code)
            | Q(ind_code_menage_camel=code)
            | Q(ben_code_menage=code)
            | Q(ben_code_menage_camel=code)
            | Q(individual__json_ext__code_menage=code)
            | Q(individual__json_ext__codeMenage=code)
        )
        results.extend(list(qs))
    elif benefit_plan.type == BenefitPlan.BenefitPlanType.GROUP_TYPE:
        qs = GroupBeneficiary.objects.filter(
            benefit_plan=benefit_plan,
            is_deleted=False,
            group__code=code,
        )
        results.extend(list(qs))

    return results


def _save_sp_beneficiary(beneficiary, audit_user):
    """HistoryBusinessModel.save avec user audit."""
    username = getattr(audit_user, 'username', None) or getattr(audit_user, 'login_name', None)
    beneficiary.save(user=audit_user, username=username)


def sync_social_protection_for_member(member, settings, audit_user, stats):
    """Suspend ou réactive le(s) bénéficiaire(s) SP liés au code_ménage du membre."""
    stats = _ensure_stats(stats)
    if not settings.sync_social_protection or not settings.benefit_plan_id:
        return stats

    code = (member.code_menage or '').strip()
    if not code:
        stats['beneficiaries_unmatched'] += 1
        stats['warnings'].append(
            f'Membre « {member} » : pas de code_ménage, mapping social protection ignoré.'
        )
        return stats

    try:
        from social_protection.models import BeneficiaryStatus
    except ImportError:
        stats['warnings'].append(
            'Module social_protection indisponible : synchronisation ignorée.'
        )
        return stats

    benefit_plan = settings.benefit_plan
    beneficiaries = _find_sp_beneficiaries(benefit_plan, code)
    if not beneficiaries:
        stats['beneficiaries_unmatched'] += 1
        stats['warnings'].append(
            f'Membre « {member} » (code_ménage={code}) : aucun bénéficiaire trouvé '
            f'sur le programme {benefit_plan.code}.'
        )
        return stats

    target_active = member.status == SereMember.Status.ACTIVE

    for beneficiary in beneficiaries:
        current = beneficiary.status
        if current == BeneficiaryStatus.GRADUATED:
            continue

        if target_active:
            if current == BeneficiaryStatus.SUSPENDED:
                beneficiary.status = BeneficiaryStatus.ACTIVE
                try:
                    _save_sp_beneficiary(beneficiary, audit_user)
                    stats['beneficiaries_reactivated'] += 1
                except Exception as exc:
                    logger.warning(
                        'Impossible de réactiver le bénéficiaire %s: %s',
                        beneficiary.pk, exc,
                    )
                    stats['warnings'].append(
                        f'Réactivation SP échouée pour code_ménage={code}: {exc}'
                    )
            # ACTIVE / POTENTIAL : laisser tel quel
        else:
            if current == BeneficiaryStatus.ACTIVE:
                beneficiary.status = BeneficiaryStatus.SUSPENDED
                try:
                    _save_sp_beneficiary(beneficiary, audit_user)
                    stats['beneficiaries_suspended'] += 1
                except Exception as exc:
                    logger.warning(
                        'Impossible de suspendre le bénéficiaire %s: %s',
                        beneficiary.pk, exc,
                    )
                    stats['warnings'].append(
                        f'Suspension SP échouée pour code_ménage={code}: {exc}'
                    )

    return stats


def apply_member_status_from_presence(
    member, audit_user, stats=None, settings=None, sync_sp=False,
):
    """
    Recalcule le statut SERE selon le nombre de présences.
    sync_sp=True uniquement après validation de la tâche subvention.
    """
    stats = _ensure_stats(stats)
    settings = settings or SereSettings.load()
    count = presence_count_for_member(member)
    new_status = status_from_presence_count(count, settings)

    if member.status != new_status:
        member.status = new_status
        _history_save_member(member, audit_user)
        stats['members_status_updated'] += 1
    else:
        stats['members_status_unchanged'] += 1

    if sync_sp:
        sync_social_protection_for_member(member, settings, audit_user, stats)
    return new_status


def recalculate_all_members_status(audit_user, stats=None, sync_sp=False):
    """Recalcule le statut SERE (et sync SP si sync_sp=True) pour tous les membres actifs."""
    stats = _ensure_stats(stats)
    settings = SereSettings.load()
    members = SereMember.objects.filter(is_deleted=False).iterator(chunk_size=200)
    for member in members:
        apply_member_status_from_presence(
            member, audit_user, stats, settings=settings, sync_sp=sync_sp,
        )
    return stats


def sync_all_members_to_social_protection(audit_user, stats=None):
    """Applique uniquement la sync SP selon les statuts SERE déjà calculés."""
    stats = _ensure_stats(stats)
    settings = SereSettings.load()
    if not settings.sync_social_protection or not settings.benefit_plan_id:
        stats['warnings'].append(
            'Sync SP désactivée ou programme non configuré dans le mapping admin.'
        )
        return stats
    for member in SereMember.objects.filter(is_deleted=False).iterator(chunk_size=200):
        sync_social_protection_for_member(member, settings, audit_user, stats)
    return stats
