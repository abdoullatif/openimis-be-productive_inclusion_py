# openIMIS Backend productive_inclusion (SERE)

## Import REST `POST /api/productive_inclusion/import/`

Paramètres multipart : `file` (obligatoire), `strategy`, `dry_run`.

- **strategy** : `INSERT` (nouveaux groupements seulement), `UPDATE` (existant seulement), `INSERT_AND_UPDATE` (défaut, upsert).
- **dry_run** : `true` / `1` / `yes` — exécution en simulation (rollback, aucune persistance).

Feuille groupements : colonnes `id`, `nom_groupement`, puis **localisation** selon l’une des deux alternatives :

1. **Hiérarchie par noms** (prioritaire si renseignée) : `region`, `prefecture`, `sous_prefecture`, `district`  
   - `district` = nom du village (Location type **V**) — **obligatoire** dans ce mode  
   - `region` → type R, `prefecture` → type D, `sous_prefecture` → type W  
2. **Identifiant village** : `localite` (ou `id_village`) = id numérique, uuid ou code d’un lieu type **V** actif  

Si la hiérarchie est fournie mais introuvable, l’import tente ensuite `localite` si présente.

Feuille membres : `id_groupement`, `nom`, `prenom`, `telephone`, `fonction`, `type_beneficiaire`, **`code_menage`** (code ménage du membre).

Feuille **activites** (3ᵉ) : `id_groupement`, `nom_activite` (nom de l’activité). Les activités sont liées au SERE ; statut initial **PLANNED**. Réimport sur un groupement traité : remplacement des activités de ce groupement (comme les membres).

GraphQL `sereMember` : champ **`codeMenage`**. Liste activités d’un SERE : **`sereActivity(groupId: …)`** (champs `title`, `status`, etc.).

Réponse JSON : compteurs `groups_created`, `groups_updated`, `groups_skipped`, `member_rows_inserted`, `members_soft_deleted`, `warnings`, `dry_run`, `strategy`.

## GraphQL `sereGroup`

Champ `locationHierarchy` : JSON `village`, `ward`, `district`, `region` (chacun `id`, `uuid`, `code`, `name`, `type`).

Champ **`membersCount`** : nombre de membres actifs (`is_deleted=false`) du groupement (agrégation sur la requête liste).

## GraphQL `sereGroupSummary`

Mêmes filtres que `sereGroup` (sans pagination) : `importCode_Icontains`, `name_Icontains`, `region_Icontains`, `prefecture_Icontains`, `subPrefecture_Icontains`, `district_Icontains`, `membersCount`, `dateUpdated_Gte` / `dateUpdated_Lte`.

Retour : `totalGroups`, `totalMembers`, `groupsByPrefecture` (`prefectureName` = niveau `locationHierarchy.district` / type D en base).

Droit liste SERE : **124001**. Récap `sereGroupSummary` : **124001**.

## Droits openIMIS (plage **124001–124009**)

Ne pas utiliser **122001–122006** : réservés au module **core** (query / create / update / delete / duplicate / replace **roles**).

| Droit | Libellé |
|-------|---------|
| 124001 | Recherche groupements SERE |
| 124002 | Création groupement SERE |
| 124003 | Mise à jour groupement SERE |
| 124004 | Suppression groupement SERE |
| 124005 | Recherche membres SERE |
| 124006 | Recherche activités SERE |
| 124007 | Création activité SERE |
| 124008 | Mise à jour activité SERE |
| 124009 | Suppression activité SERE |

Import REST : **124001** (même droit que la liste SERE).
