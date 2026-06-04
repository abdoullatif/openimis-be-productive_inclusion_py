"""
Résolution des localisations openIMIS (Location) pour les imports SERE et l'affichage hiérarchique.
Les types courants : V = village, W = sous-district / ward, D = district, R = région.
"""

import math

from location.models import Location


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
