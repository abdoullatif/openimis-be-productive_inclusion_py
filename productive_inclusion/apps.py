from django.apps import AppConfig

MODULE_NAME = 'productive_inclusion'

DEFAULT_CONFIG = {
    'gql_sere_group_search_perms': ['122001'],
    'gql_sere_group_create_perms': ['122002'],
    'gql_sere_group_update_perms': ['122003'],
    'gql_sere_group_delete_perms': ['122004'],
    'gql_sere_member_search_perms': ['122005'],
    'gql_sere_activity_search_perms': ['122006'],
    'gql_sere_activity_create_perms': ['122007'],
    'gql_sere_activity_update_perms': ['122008'],
    'gql_sere_activity_delete_perms': ['122009'],
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
