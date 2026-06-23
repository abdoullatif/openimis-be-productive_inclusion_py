from django.apps import AppConfig

MODULE_NAME = 'productive_inclusion'

DEFAULT_CONFIG = {
  # Plage 124xxx dédiée — ne pas réutiliser 122001-122006 (core : gestion des rôles).
    'gql_sere_group_search_perms': ['124001'],
    'gql_sere_group_create_perms': ['124002'],
    'gql_sere_group_update_perms': ['124003'],
    'gql_sere_group_delete_perms': ['124004'],
    'gql_sere_member_search_perms': ['124005'],
    'gql_sere_activity_search_perms': ['124006'],
    'gql_sere_activity_create_perms': ['124007'],
    'gql_sere_activity_update_perms': ['124008'],
    'gql_sere_activity_delete_perms': ['124009'],
}


class ProductiveInclusionConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = MODULE_NAME
    verbose_name = 'Productive Inclusion'

    gql_sere_group_search_perms = None
    gql_sere_group_create_perms = None
    gql_sere_group_update_perms = None
    gql_sere_group_delete_perms = None
    gql_sere_member_search_perms = None
    gql_sere_activity_search_perms = None
    gql_sere_activity_create_perms = None
    gql_sere_activity_update_perms = None
    gql_sere_activity_delete_perms = None

    def ready(self):
        from core.models import ModuleConfiguration

        cfg = ModuleConfiguration.get_or_default(MODULE_NAME, DEFAULT_CONFIG)
        self.__load_config(cfg)

    @classmethod
    def __load_config(cls, cfg):
        for field in cfg:
            if hasattr(ProductiveInclusionConfig, field):
                setattr(ProductiveInclusionConfig, field, cfg[field])
