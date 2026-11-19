import logging
import re

import pandas as pd
from django.db import transaction
from django.db.models import Q

from productive_inclusion.location_utils import (
    resolve_village_by_admin_names,
    resolve_village_location,
)
from productive_inclusion.models import (
    SereActivity,
    SereGroup,
    SereMember,
    SereMemberPresence,
)

logger = logging.getLogger(__name__)


class SereImportStrategy:
    INSERT = 'INSERT'
    UPDATE = 'UPDATE'
    INSERT_AND_UPDATE = 'INSERT_AND_UPDATE'

    ALLOWED = {INSERT, UPDATE, INSERT_AND_UPDATE}


GROUP_SHEET_ALIASES = {
    'id': 'import_code',
    'id_groupement': 'import_code',
    'code_groupement': 'import_code',
    'nom_groupement': 'name',
    'groupement': 'name',
    'nom': 'name',
    # Alternative 1 : id / uuid / code du village (Location type V)
    'localite': 'village_id',
    'localité': 'village_id',
    'id_village': 'village_id',
    'id_village_uuid': 'village_id',
    # Alternative 2 : hiérarchie administrative par noms
    'region': 'region',
    'région': 'region',
    'prefecture': 'prefecture',
    'préfecture': 'prefecture',
    'sous_prefecture': 'sous_prefecture',
    'sous_préfecture': 'sous_prefecture',
    'sousprefecture': 'sous_prefecture',
    'district': 'district',
}

MEMBER_SHEET_ALIASES = {
    'id': 'import_code',
    'id_groupement': 'import_code',
    'code_groupement': 'import_code',
    'nom': 'last_name',
    'prenom': 'first_name',
    'prénom': 'first_name',
    'telephone': 'phone',
    'téléphone': 'phone',
    'fonction': 'role',
    'type_beneficiaire': 'beneficiary_type',
    'type_bénéficiaire': 'beneficiary_type',
    'code_menage': 'code_menage',
    'code_ménage': 'code_menage',
    'nombre_presences': 'presence_count',
    'nombre_présences': 'presence_count',
    'nb_presences': 'presence_count',
    'nb_présences': 'presence_count',
    'nbre_presences': 'presence_count',
    'presences': 'presence_count',
    'présences': 'presence_count',
    'presence_count': 'presence_count',
    'presencecount': 'presence_count',
}

# Plafond pour éviter des imports accidentels trop volumineux.
MAX_PRESENCE_COUNT = 500

ACTIVITY_SHEET_ALIASES = {
    'id': 'import_code',
    'id_groupement': 'import_code',
    'code_groupement': 'import_code',
    'nom_activite': 'title',
    'nom_de_lactivite': 'title',
    'nom_de_l_activite': 'title',
    'activite': 'title',
    'activité': 'title',
    'titre': 'title',
    'title': 'title',
}

SHEET_GROUPEMENTS = ('groupements',)
SHEET_MEMBRES = ('membres',)
SHEET_ACTIVITES = ('activites', 'activités')


def _normalize_header(value):
    if value is None:
        return ''
    normalized = str(value).strip().lower()
    normalized = normalized.replace(' ', '_')
    return re.sub(r'[^a-z0-9_àâäéèêëîïôöùûüç]', '', normalized)


def _normalize_dataframe(df, aliases):
    renamed = {}
    for column in df.columns:
        key = _normalize_header(column)
        if key in aliases:
            renamed[column] = aliases[key]
    return df.rename(columns=renamed)


def _clean_value(value):
    if value is None or pd.isna(value):
        return None
    value = str(value).strip()
    return value or None


def _resolve_audit_user(user):
    """
    Utilisateur core pour HistoryModel.save(user=...).
    Recharge depuis la base pour garantir username et clé primaire valides (JWT/REST).
    """
    from core.models import User as CoreUser

    if user is None:
        raise ValueError('Utilisateur requis pour l\'enregistrement.')

    if isinstance(user, CoreUser) and user.pk:
        found = CoreUser.objects.filter(pk=user.pk).first()
        if found and found.username:
            return found

    for candidate in (
        getattr(user, 'username', None),
        getattr(user, 'login_name', None),
        getattr(getattr(user, 'i_user', None), 'login_name', None),
    ):
        if candidate:
            found = CoreUser.objects.filter(username=candidate).first()
            if found:
                return found

    raise ValueError(
        'Impossible d\'enregistrer: fournir un utilisateur avec username ou login_name valide.'
    )


def _history_save(instance, audit_user):
    """Enregistrement HistoryModel avec user et username (double filet)."""
    instance.save(user=audit_user, username=audit_user.username)


def _history_save_if_changed(instance, audit_user):
    """
    HistoryModel refuse save() sans changement de champs.
    Réimport identique : pas de save groupement, mais l'appelant peut
    tout de même traiter membres/activités pour ce groupement.
    """
    if instance.id is None or instance.is_dirty(check_relationship=True):
        _history_save(instance, audit_user)
        return True
    return False


def _parse_presence_count(row):
    """
    Lit nombre_presences depuis la ligne Excel.
    None = cellule vide / colonne absente → ne pas modifier le compteur.
    """
    raw = row.get('presence_count') if hasattr(row, 'get') else None
    if raw is None or (isinstance(raw, float) and pd.isna(raw)):
        return None
    text = str(raw).strip()
    if text == '' or text.lower() in ('nan', 'none', 'null'):
        return None
    try:
        value = int(float(text.replace(',', '.')))
    except (TypeError, ValueError):
        raise ValueError(f'Nombre de présences invalide: {raw!r} (entier attendu).')
    if value < 0:
        raise ValueError(f'Nombre de présences négatif interdit: {value}.')
    if value > MAX_PRESENCE_COUNT:
        raise ValueError(
            f'Nombre de présences trop élevé ({value}). Maximum autorisé: {MAX_PRESENCE_COUNT}.'
        )
    return value


def _apply_member_presence_count(member, target_count, audit_user, stats):
    """Met à jour SereMember.presence_count (source de vérité)."""
    current = int(member.presence_count or 0)
    if current == target_count:
        stats['presences_unchanged'] += 1
        return False
    member.presence_count = target_count
    _history_save(member, audit_user)
    stats['presences_created'] += 1
    return True


def _member_fields_from_row(row):
    return {
        'last_name': _clean_value(row.get('last_name')),
        'first_name': _clean_value(row.get('first_name')),
        'phone': _clean_value(row.get('phone')),
        'role': _clean_value(row.get('role')),
        'beneficiary_type': _clean_value(row.get('beneficiary_type')),
        'code_menage': _clean_value(row.get('code_menage')),
    }


def _find_existing_member(group, fields):
    """Correspondance : code_ménage si renseigné, sinon nom + prénom (y compris soft-deleted)."""
    qs = SereMember.objects.filter(group=group)
    code_menage = fields.get('code_menage')
    if code_menage:
        return qs.filter(code_menage=code_menage).order_by('is_deleted').first()
    last_name = fields['last_name']
    first_name = fields.get('first_name')
    qs = qs.filter(last_name=last_name)
    if first_name:
        return qs.filter(first_name=first_name).order_by('is_deleted').first()
    return qs.filter(Q(first_name__isnull=True) | Q(first_name='')).order_by('is_deleted').first()


def _find_existing_activity(group, title):
    return SereActivity.objects.filter(
        group=group,
        title=title,
    ).order_by('is_deleted').first()


class SereImportService:
    def __init__(self, user):
        self.user = user
        self._audit_user = _resolve_audit_user(user)

    def import_file(self, import_file, strategy=SereImportStrategy.INSERT_AND_UPDATE, dry_run=False):
        strategy = (strategy or SereImportStrategy.INSERT_AND_UPDATE).upper()
        if strategy not in SereImportStrategy.ALLOWED:
            raise ValueError(
                f'Stratégie invalide: {strategy}. Valeurs: INSERT, UPDATE, INSERT_AND_UPDATE.'
            )

        groups_df, members_df, activities_df = self._read_workbook(import_file)
        groups_df = _normalize_dataframe(groups_df, GROUP_SHEET_ALIASES)
        members_df = _normalize_dataframe(members_df, MEMBER_SHEET_ALIASES)
        activities_df = _normalize_dataframe(activities_df, ACTIVITY_SHEET_ALIASES)

        self._validate_groups_dataframe(groups_df)
        self._validate_members_dataframe(members_df)
        self._validate_activities_dataframe(activities_df)

        stats = {
            'success': True,
            'dry_run': bool(dry_run),
            'strategy': strategy,
            'groups_created': 0,
            'groups_updated': 0,
            'groups_unchanged': 0,
            'groups_skipped': 0,
            'member_rows_inserted': 0,
            'member_rows_updated': 0,
            'member_rows_unchanged': 0,
            'member_rows_skipped': 0,
            'activity_rows_inserted': 0,
            'activity_rows_updated': 0,
            'activity_rows_unchanged': 0,
            'activity_rows_skipped': 0,
            'presences_created': 0,
            'presences_deleted': 0,
            'presences_unchanged': 0,
            'members_status_updated': 0,
            'members_status_unchanged': 0,
            'beneficiaries_suspended': 0,
            'beneficiaries_reactivated': 0,
            'beneficiaries_unmatched': 0,
            'warnings': [],
        }

        with transaction.atomic():
            groups_touched = self._import_groups(groups_df, strategy, stats)
            self._import_members(members_df, groups_touched, strategy, stats)
            self._import_activities(activities_df, groups_touched, strategy, stats)
            if dry_run:
                transaction.set_rollback(True)

        stats['groups_touched_count'] = len(groups_touched)
        return stats

    def _read_sheet_by_name(self, workbook, names_lower, fallback_index):
        for key in names_lower:
            if key in workbook.sheet_names_lower:
                return pd.read_excel(workbook, sheet_name=workbook.sheet_names_lower[key])
        if fallback_index is not None and len(workbook.sheet_names) > fallback_index:
            return pd.read_excel(workbook, sheet_name=workbook.sheet_names[fallback_index])
        return None

    def _read_workbook(self, import_file):
        file_name = getattr(import_file, 'name', '').lower()
        if file_name.endswith('.xlsx') or file_name.endswith('.xls'):
            workbook = pd.ExcelFile(import_file)
            workbook.sheet_names_lower = {
                name.lower().strip(): name for name in workbook.sheet_names
            }
            if len(workbook.sheet_names) < 3:
                raise ValueError(
                    'Le fichier doit contenir trois feuilles: groupements, membres et activites.'
                )
            groups_df = self._read_sheet_by_name(workbook, SHEET_GROUPEMENTS, 0)
            members_df = self._read_sheet_by_name(workbook, SHEET_MEMBRES, 1)
            activities_df = self._read_sheet_by_name(workbook, SHEET_ACTIVITES, 2)
            if groups_df is None or members_df is None or activities_df is None:
                raise ValueError(
                    'Feuilles requises: groupements (1), membres (2), activites (3).'
                )
            return groups_df, members_df, activities_df

        raise ValueError(
            'Le fichier doit être au format Excel (.xlsx ou .xls) avec trois feuilles.'
        )

    def _validate_groups_dataframe(self, groups_df):
        missing = {'import_code', 'name'} - set(groups_df.columns)
        if missing:
            raise ValueError(
                'La première feuille doit contenir au minimum les colonnes id et nom du groupement.'
            )

    def _validate_members_dataframe(self, members_df):
        missing = {'import_code', 'last_name'} - set(members_df.columns)
        if missing:
            raise ValueError(
                'La deuxième feuille doit contenir au minimum les colonnes id_groupement et nom.'
            )

    def _validate_activities_dataframe(self, activities_df):
        missing = {'import_code', 'title'} - set(activities_df.columns)
        if missing:
            raise ValueError(
                'La feuille activites doit contenir au minimum id_groupement et nom_activite (ou nom de l\'activité).'
            )

    def _resolve_village_for_row(self, row, stats):
        """
        Deux alternatives (priorité à la hiérarchie nominative si renseignée) :
        1) region + prefecture + sous_prefecture + district (noms)
        2) localite / id_village (id, uuid ou code du lieu type V)
        """
        region = _clean_value(row.get('region')) if 'region' in row.index else None
        prefecture = _clean_value(row.get('prefecture')) if 'prefecture' in row.index else None
        sous_prefecture = (
            _clean_value(row.get('sous_prefecture')) if 'sous_prefecture' in row.index else None
        )
        district = _clean_value(row.get('district')) if 'district' in row.index else None
        has_hierarchy_values = any((region, prefecture, sous_prefecture, district))

        if has_hierarchy_values:
            if not district:
                stats['warnings'].append(
                    'Localisation hiérarchique incomplète: la colonne district (village) est obligatoire '
                    'lorsque region/prefecture/sous_prefecture/district sont utilisés.'
                )
            else:
                loc = resolve_village_by_admin_names(
                    region=region,
                    prefecture=prefecture,
                    sous_prefecture=sous_prefecture,
                    district=district,
                )
                if loc:
                    return loc, loc.name
                stats['warnings'].append(
                    'Village introuvable pour la hiérarchie '
                    f'region={region!r}, prefecture={prefecture!r}, '
                    f'sous_prefecture={sous_prefecture!r}, district={district!r}.'
                )

        if 'village_id' not in getattr(row, 'index', []):
            return None, None
        raw = row.get('village_id')
        if raw is None or (isinstance(raw, float) and pd.isna(raw)):
            return None, None

        loc = resolve_village_location(raw)
        if not loc:
            stats['warnings'].append(
                f'Village introuvable ou inactif pour la valeur {raw!r} '
                f'(attendu: id, uuid ou code d\'un lieu type V).'
            )
            return None, None
        return loc, loc.name

    def _import_groups(self, groups_df, strategy, stats):
        """Retourne import_code -> SereGroup uniquement pour les groupements réellement écrits."""
        groups_touched = {}
        for _, row in groups_df.iterrows():
            import_code = _clean_value(row.get('import_code'))
            name = _clean_value(row.get('name'))
            if not import_code or not name:
                continue

            location, locality_label = self._resolve_village_for_row(row, stats)

            # Unique sur import_code : inclure les soft-deleted pour pouvoir réactiver après reset.
            existing = SereGroup.objects.filter(import_code=import_code).first()

            if strategy == SereImportStrategy.INSERT:
                if existing and not existing.is_deleted:
                    stats['groups_skipped'] += 1
                    stats['warnings'].append(
                        f'Groupement {import_code}: déjà existant, ignoré (stratégie INSERT).'
                    )
                    continue
                if existing and existing.is_deleted:
                    existing.name = name
                    existing.locality = locality_label
                    existing.location = location
                    existing.is_deleted = False
                    _history_save(existing, self._audit_user)
                    stats['groups_created'] += 1
                    groups_touched[import_code] = existing
                    continue
                group = SereGroup(
                    import_code=import_code,
                    name=name,
                    locality=locality_label,
                    location=location,
                )
                _history_save(group, self._audit_user)
                stats['groups_created'] += 1
                groups_touched[import_code] = group
                continue

            if strategy == SereImportStrategy.UPDATE:
                if not existing:
                    stats['groups_skipped'] += 1
                    stats['warnings'].append(
                        f'Groupement {import_code}: inexistant, ignoré (stratégie UPDATE).'
                    )
                    continue
                existing.name = name
                existing.locality = locality_label
                existing.location = location
                existing.is_deleted = False
                if _history_save_if_changed(existing, self._audit_user):
                    stats['groups_updated'] += 1
                else:
                    stats['groups_unchanged'] += 1
                groups_touched[import_code] = existing
                continue

            # INSERT_AND_UPDATE
            if existing:
                existing.name = name
                existing.locality = locality_label
                existing.location = location
                existing.is_deleted = False
                if _history_save_if_changed(existing, self._audit_user):
                    stats['groups_updated'] += 1
                else:
                    stats['groups_unchanged'] += 1
                groups_touched[import_code] = existing
            else:
                group = SereGroup(
                    import_code=import_code,
                    name=name,
                    locality=locality_label,
                    location=location,
                )
                _history_save(group, self._audit_user)
                stats['groups_created'] += 1
                groups_touched[import_code] = group

        return groups_touched

    def _import_members(self, members_df, groups_touched, strategy, stats):
        for _, row in members_df.iterrows():
            import_code = _clean_value(row.get('import_code'))
            fields = _member_fields_from_row(row)
            last_name = fields['last_name']
            if not import_code or not last_name:
                continue

            try:
                presence_count = _parse_presence_count(row)
            except ValueError as exc:
                raise ValueError(f'Membre « {last_name} » ({import_code}): {exc}') from exc

            group = groups_touched.get(import_code)
            if not group:
                if not SereGroup.objects.filter(import_code=import_code, is_deleted=False).exists():
                    raise ValueError(
                        f'Groupement introuvable pour l\'identifiant {import_code} '
                        f'(aucune ligne correspondante sur la feuille groupements).'
                    )
                stats['warnings'].append(
                    f'Membre « {last_name} » : groupement {import_code} non traité dans cet import '
                    f'(seuls les groupements traités sur la feuille groupements reçoivent des membres).'
                )
                continue

            existing = _find_existing_member(group, fields)
            label = f'{last_name} {fields.get("first_name") or ""}'.strip()
            member = None

            if strategy == SereImportStrategy.INSERT:
                if existing and not existing.is_deleted:
                    stats['member_rows_skipped'] += 1
                    member = existing
                elif existing and existing.is_deleted:
                    for key in ('last_name', 'first_name', 'phone', 'role', 'beneficiary_type', 'code_menage'):
                        setattr(existing, key, fields[key])
                    existing.is_deleted = False
                    _history_save(existing, self._audit_user)
                    stats['member_rows_inserted'] += 1
                    member = existing
                else:
                    member = SereMember(group=group, **fields)
                    _history_save(member, self._audit_user)
                    stats['member_rows_inserted'] += 1

            elif strategy == SereImportStrategy.UPDATE:
                if not existing:
                    stats['member_rows_skipped'] += 1
                    stats['warnings'].append(
                        f'Membre « {label} » ({import_code}) : inexistant, ignoré (stratégie UPDATE).'
                    )
                else:
                    for key in ('last_name', 'first_name', 'phone', 'role', 'beneficiary_type', 'code_menage'):
                        setattr(existing, key, fields[key])
                    existing.is_deleted = False
                    if _history_save_if_changed(existing, self._audit_user):
                        stats['member_rows_updated'] += 1
                    else:
                        stats['member_rows_unchanged'] += 1
                    member = existing

            else:
                # INSERT_AND_UPDATE
                if existing:
                    for key in ('last_name', 'first_name', 'phone', 'role', 'beneficiary_type', 'code_menage'):
                        setattr(existing, key, fields[key])
                    existing.is_deleted = False
                    if _history_save_if_changed(existing, self._audit_user):
                        stats['member_rows_updated'] += 1
                    else:
                        stats['member_rows_unchanged'] += 1
                    member = existing
                else:
                    member = SereMember(group=group, **fields)
                    _history_save(member, self._audit_user)
                    stats['member_rows_inserted'] += 1

            if member is not None and presence_count is not None:
                _apply_member_presence_count(
                    member, presence_count, self._audit_user, stats,
                )
                from productive_inclusion.status_eligibility import (
                    apply_member_status_from_presence,
                )
                apply_member_status_from_presence(
                    member, self._audit_user, stats, sync_sp=False,
                )

        return stats

    def _import_activities(self, activities_df, groups_touched, strategy, stats):
        for _, row in activities_df.iterrows():
            import_code = _clean_value(row.get('import_code'))
            title = _clean_value(row.get('title'))
            if not import_code or not title:
                continue

            group = groups_touched.get(import_code)
            if not group:
                if not SereGroup.objects.filter(import_code=import_code, is_deleted=False).exists():
                    raise ValueError(
                        f'Groupement introuvable pour l\'activité « {title} » (id {import_code}).'
                    )
                stats['warnings'].append(
                    f'Activité « {title} » : groupement {import_code} non traité dans cet import, ligne ignorée.'
                )
                continue

            existing = _find_existing_activity(group, title)

            if strategy == SereImportStrategy.INSERT:
                if existing and not existing.is_deleted:
                    stats['activity_rows_skipped'] += 1
                    continue
                if existing and existing.is_deleted:
                    existing.is_deleted = False
                    _history_save(existing, self._audit_user)
                    stats['activity_rows_inserted'] += 1
                    continue
                activity = SereActivity(
                    group=group,
                    title=title,
                    status=SereActivity.Status.PLANNED,
                )
                _history_save(activity, self._audit_user)
                stats['activity_rows_inserted'] += 1
                continue

            if strategy == SereImportStrategy.UPDATE:
                if not existing:
                    stats['activity_rows_skipped'] += 1
                    stats['warnings'].append(
                        f'Activité « {title} » ({import_code}) : inexistante, ignorée (stratégie UPDATE).'
                    )
                    continue
                existing.is_deleted = False
                if _history_save_if_changed(existing, self._audit_user):
                    stats['activity_rows_updated'] += 1
                else:
                    stats['activity_rows_unchanged'] += 1
                continue

            # INSERT_AND_UPDATE
            if existing:
                existing.is_deleted = False
                if _history_save_if_changed(existing, self._audit_user):
                    stats['activity_rows_updated'] += 1
                else:
                    stats['activity_rows_unchanged'] += 1
            else:
                activity = SereActivity(
                    group=group,
                    title=title,
                    status=SereActivity.Status.PLANNED,
                )
                _history_save(activity, self._audit_user)
                stats['activity_rows_inserted'] += 1

        return stats


class SereActivityService:
    @staticmethod
    def create(user, data):
        activity = SereActivity(**data)
        _history_save(activity, _resolve_audit_user(user))
        return activity

    @staticmethod
    def update(user, activity, data):
        for field, value in data.items():
            setattr(activity, field, value)
        _history_save(activity, _resolve_audit_user(user))
        return activity

    @staticmethod
    def delete(user, activity):
        activity.is_deleted = True
        _history_save(activity, _resolve_audit_user(user))
        return activity


class SereResetService:
    """
    Purge (soft-delete) de toutes les données SERE actives :
    activités, présences, membres, groupements.
    """

    @staticmethod
    def reset_all(user):
        audit_user = _resolve_audit_user(user)
        with transaction.atomic():
            activities_deleted = SereActivity.objects.filter(is_deleted=False).update(
                is_deleted=True,
            )
            presences_deleted = SereMemberPresence.objects.filter(is_deleted=False).update(
                is_deleted=True,
            )
            members_deleted = SereMember.objects.filter(is_deleted=False).update(
                is_deleted=True,
            )
            groups_deleted = SereGroup.objects.filter(is_deleted=False).update(
                is_deleted=True,
            )

        logger.info(
            'SERE reset by %s: groups=%s members=%s activities=%s presences=%s',
            getattr(audit_user, 'username', audit_user),
            groups_deleted,
            members_deleted,
            activities_deleted,
            presences_deleted,
        )
        return {
            'success': True,
            'groups_deleted': groups_deleted,
            'members_deleted': members_deleted,
            'activities_deleted': activities_deleted,
            'presences_deleted': presences_deleted,
        }
