import io
import logging
import mimetypes
import os

import pandas as pd
from django.core.exceptions import ValidationError
from django.http import HttpResponse
from django.utils.translation import gettext as _
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response

from im_export.views import check_user_rights
from productive_inclusion.apps import ProductiveInclusionConfig
from productive_inclusion.services import (
    SereImportService,
    SereImportStrategy,
    SereResetService,
    _resolve_audit_user,
)

logger = logging.getLogger(__name__)

ALLOWED_EXTENSIONS = {'.xlsx', '.xls'}
ALLOWED_MIME_TYPES = {
    'application/vnd.ms-excel',
    'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
}

mimetypes.add_type('application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', '.xlsx')
mimetypes.add_type('application/vnd.ms-excel', '.xls')


def _is_valid_file(import_file):
    file_extension = os.path.splitext(import_file.name)[1].lower()
    if file_extension not in ALLOWED_EXTENSIONS:
        return False, _('Le fichier doit être au format Excel (.xlsx ou .xls) avec trois feuilles.')

    file_mime_type, _ = mimetypes.guess_type(import_file.name)
    if file_mime_type and file_mime_type not in ALLOWED_MIME_TYPES:
        return False, _(f'Type MIME invalide: {file_mime_type}')

    return True, None


@api_view(['GET'])
@permission_classes([check_user_rights(ProductiveInclusionConfig.gql_sere_group_search_perms)])
def download_sere_import_template(request):
    try:
        # Deux alternatives de localisation (au choix) :
        # - region/prefecture/sous_prefecture/district (noms)
        # - localite (id, uuid ou code du village type V)
        groups_df = pd.DataFrame(
            columns=[
                'id',
                'nom_groupement',
                'region',
                'prefecture',
                'sous_prefecture',
                'district',
                'localite',
            ]
        )
        members_df = pd.DataFrame(
            columns=[
                'id_groupement', 'nom', 'prenom', 'telephone', 'fonction',
                'type_beneficiaire', 'code_menage', 'nombre_presences',
            ]
        )
        activities_df = pd.DataFrame(
            columns=['id_groupement', 'nom_activite'],
        )
        buffer = io.BytesIO()
        with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
            groups_df.to_excel(writer, sheet_name='groupements', index=False)
            members_df.to_excel(writer, sheet_name='membres', index=False)
            activities_df.to_excel(writer, sheet_name='activites', index=False)
        buffer.seek(0)
        response = HttpResponse(
            buffer.getvalue(),
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        )
        response['Content-Disposition'] = 'attachment; filename="sere_import_template.xlsx"'
        return response
    except Exception as exc:
        logger.error('Unexpected error while generating SERE import template', exc_info=exc)
        return Response({'success': False, 'error': str(exc)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['POST'])
@permission_classes([check_user_rights(ProductiveInclusionConfig.gql_sere_group_delete_perms)])
def reset_sere_data(request):
    """
    Soft-delete de tous les groupements SERE, membres, activités et présences actifs.
    Droit requis : 124004 (suppression SERE).
    """
    try:
        result = SereResetService.reset_all(request.user)
        return Response(result, status=status.HTTP_200_OK)
    except ValueError as exc:
        logger.error('Error while resetting SERE data', exc_info=exc)
        return Response({'success': False, 'error': str(exc)}, status=status.HTTP_400_BAD_REQUEST)
    except Exception as exc:
        logger.error('Unexpected error while resetting SERE data', exc_info=exc)
        return Response({'success': False, 'error': str(exc)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['POST'])
@permission_classes([check_user_rights(ProductiveInclusionConfig.gql_sere_presence_validate_perms)])
def validate_sere_presences(request):
    """
    Recalcule les statuts SERE et crée une tâche subvention (assignable).
    La sync SP s'applique uniquement à la complétion de la tâche.
    Droit requis : 124010.
    """
    try:
        from productive_inclusion.subsidy_task import create_presence_validation_task

        result = create_presence_validation_task(request.user)
        if not result.get('success'):
            return Response(result, status=status.HTTP_400_BAD_REQUEST)
        return Response(result, status=status.HTTP_201_CREATED)
    except ValueError as exc:
        logger.error('Error while creating SERE subvention task', exc_info=exc)
        return Response({'success': False, 'error': str(exc)}, status=status.HTTP_400_BAD_REQUEST)
    except Exception as exc:
        logger.error('Unexpected error while creating SERE subvention task', exc_info=exc)
        return Response({'success': False, 'error': str(exc)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['POST'])
@permission_classes([check_user_rights(ProductiveInclusionConfig.gql_sere_group_search_perms)])
def import_sere_groups(request):
    import_file = request.FILES.get('file')
    if not import_file:
        return Response({'success': False, 'error': _('Fichier manquant.')}, status=status.HTTP_400_BAD_REQUEST)

    is_valid, error_message = _is_valid_file(import_file)
    if not is_valid:
        return Response({'success': False, 'error': error_message}, status=status.HTTP_400_BAD_REQUEST)

    try:
        strategy = request.POST.get('strategy', SereImportStrategy.INSERT_AND_UPDATE)
        dry_run = str(request.POST.get('dry_run', '')).lower() in ('1', 'true', 'yes', 'on')
        audit_user = _resolve_audit_user(request.user)
        result = SereImportService(audit_user).import_file(
            import_file,
            strategy=strategy,
            dry_run=dry_run,
        )
        return Response(result, status=status.HTTP_201_CREATED)
    except ValidationError as exc:
        logger.error('Validation error while importing SERE groups', exc_info=exc)
        return Response(
            {'success': False, 'error': exc.messages if hasattr(exc, 'messages') else str(exc)},
            status=status.HTTP_400_BAD_REQUEST,
        )
    except ValueError as exc:
        logger.error('Error while importing SERE groups', exc_info=exc)
        return Response({'success': False, 'error': str(exc)}, status=status.HTTP_400_BAD_REQUEST)
    except Exception as exc:
        logger.error('Unexpected error while importing SERE groups', exc_info=exc)
        return Response({'success': False, 'error': str(exc)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
