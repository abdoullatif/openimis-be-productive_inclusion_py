from django.urls import path

from productive_inclusion.views import download_sere_import_template, import_sere_groups

urlpatterns = [
    path('import_template/', download_sere_import_template),
    path('import/', import_sere_groups),
]
