"""
Résolution des localisations openIMIS (Location) pour les imports SERE et l'affichage hiérarchique.
Les types courants : V = village, W = sous-district / ward, D = district, R = région.

Correspondance libellés import ↔ types Location (alignée UI Inclusion productive) :
  region          → R
  prefecture      → D
  sous_prefecture → W
  district        → V  (village / district au sens métier)
"""

import math
import unicodedata

from location.models import Location


def _strip_accents(value):
    if value is None:
        return ''
    normalized = unicodedata.normalize('NFKD', str(value))
    return ''.join(ch for ch in normalized if not unicodedata.combining(ch))


def resolve_village_location(raw):
    """
    Retourne un Location de type village (V) actif à partir d'un identifiant :
    id numérique, uuid (chaîne), ou code village.
    """
    if raw is None:
        return None
    if isinstance(raw, float):
        if math.isnan(raw):
            return None
        if abs(raw - int(raw)) < 1e-9:
            raw = int(raw)
    try:
        if hasattr(raw, 'item'):
            raw = raw.item()
    except Exception:
        pass
    s = str(raw).strip()
    if not s or s.lower() == 'nan':
        return None

    base = Location.objects.filter(validity_to__isnull=True, type='V')

    if s.isdigit():
        loc = base.filter(id=int(s)).first()
        if loc:
            return loc

    loc = base.filter(uuid__iexact=s).first()
    if loc:
        return loc

    return base.filter(code=s).first()


def _find_location_by_name(name, loc_type, parent=None):
    """
    Cherche un Location actif par nom (iexact, puis icontains si unique).
    Si parent est fourni, restreint aux enfants de ce parent.
    """
    if not name:
        return None
    name = str(name).strip()
    if not name:
        return None

    qs = Location.objects.filter(validity_to__isnull=True, type=loc_type)
    if parent is not None:
        qs = qs.filter(parent=parent)

    exact = list(qs.filter(name__iexact=name)[:2])
    if len(exact) == 1:
        return exact[0]
    if len(exact) > 1:
        return None

    loose = list(qs.filter(name__icontains=name)[:2])
    if len(loose) == 1:
        return loose[0]
    if len(loose) > 1:
        return None

    # Dernier recours : égalité sans accents sur un échantillon borné (parent restreint)
    if parent is not None or qs.count() <= 200:
        target = _strip_accents(name).casefold()
        accent_matches = [
            loc for loc in qs.iterator()
            if _strip_accents(loc.name).casefold() == target
        ]
        if len(accent_matches) == 1:
            return accent_matches[0]
    return None


def resolve_village_by_admin_names(
    region=None,
    prefecture=None,
    sous_prefecture=None,
    district=None,
):
    """
    Résout un village (type V) via la hiérarchie administrative nominative.

    Ordre : region (R) → prefecture (D) → sous_prefecture (W) → district (V).
    Les niveaux fournis restreignent la recherche ; `district` (nom du village) est requis.
    """
    district_name = (str(district).strip() if district is not None else '') or None
    if not district_name:
        return None

    parent = None
    chain = (
        (region, 'R'),
        (prefecture, 'D'),
        (sous_prefecture, 'W'),
    )
    for raw_name, loc_type in chain:
        name = (str(raw_name).strip() if raw_name is not None else '') or None
        if not name:
            continue
        found = _find_location_by_name(name, loc_type, parent=parent)
        if not found:
            # Niveau fourni mais introuvable sous le parent courant → échec
            return None
        parent = found

    return _find_location_by_name(district_name, 'V', parent=parent)


def _level_dict(loc):
    if not loc:
        return None
    return {
        'id': loc.id,
        'uuid': loc.uuid,
        'code': loc.code,
        'name': loc.name,
        'type': loc.type,
    }


def build_location_hierarchy_dict(village_location):
    """
    À partir d'un noeud Location (idéalement type V), remonte la chaîne parent
    et renvoie village, ward (municipalité / sous-district), district, region.
    """
    if not village_location:
        return None

    by_type = {}
    node = village_location
    depth = 0
    while node is not None and depth < 10:
        by_type[node.type] = node
        node = node.parent
        depth += 1

    return {
        'village': _level_dict(by_type.get('V')),
        'ward': _level_dict(by_type.get('W')),
        'district': _level_dict(by_type.get('D')),
        'region': _level_dict(by_type.get('R')),
    }


def location_labels_for_member_list(village_location):
    """
    Libellés plats pour la grille Membres — mêmes clés que locationHierarchy JSON :
    - district_name ← village (V)
    - sub_prefecture_name ← ward (W)
    - prefecture_name ← district (D)
    """
    hierarchy = build_location_hierarchy_dict(village_location)
    if not hierarchy:
        return {
            'district_name': None,
            'sub_prefecture_name': None,
            'prefecture_name': None,
        }
    village = hierarchy.get('village') or {}
    ward = hierarchy.get('ward') or {}
    district = hierarchy.get('district') or {}
    return {
        'district_name': village.get('name'),
        'sub_prefecture_name': ward.get('name'),
        'prefecture_name': district.get('name'),
    }
