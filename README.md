# openIMIS Backend productive_inclusion (SERE)

## Import REST `POST /api/productive_inclusion/import/`

Paramètres multipart : `file` (obligatoire), `strategy`, `dry_run`.

- **strategy** : `INSERT` (nouveaux groupements seulement), `UPDATE` (existant seulement), `INSERT_AND_UPDATE` (défaut, upsert).
- **dry_run** : `true` / `1` / `yes` — exécution en simulation (rollback, aucune persistance).

Feuille groupements : colonnes `id`, `nom_groupement`, `localite` (ou `id_village`) = **identifiant du village** (id numérique, uuid ou code ; lieu type **V** actif).

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

Droit : **122001** (comme la liste). L’ancien argument `search` sur `sereGroup` est retiré.
