from django.urls import path

from productive_inclusion.views import (
    download_sere_import_template,
    import_sere_groups,
    reset_sere_data,
    validate_sere_presences,
)

urlpatterns = [
    path('import_template/', download_sere_import_template),
    path('import/', import_sere_groups),
    path('reset/', reset_sere_data),
    path('validate_presences/', validate_sere_presences),
]
