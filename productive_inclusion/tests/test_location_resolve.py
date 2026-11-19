from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase

from productive_inclusion.location_utils import resolve_village_by_admin_names
from productive_inclusion.services import SereImportService


class ResolveVillageByAdminNamesTests(SimpleTestCase):
    def test_requires_district(self):
        self.assertIsNone(
            resolve_village_by_admin_names(
                region='Conakry',
                prefecture='Kaloum',
                sous_prefecture='Centre',
                district=None,
            )
        )

    @patch('productive_inclusion.location_utils._find_location_by_name')
    def test_walks_hierarchy(self, mock_find):
        region = MagicMock(name='R')
        prefecture = MagicMock(name='D')
        ward = MagicMock(name='W')
        village = MagicMock(name='V')
        mock_find.side_effect = [region, prefecture, ward, village]

        result = resolve_village_by_admin_names(
            region='Conakry',
            prefecture='Kaloum',
            sous_prefecture='Centre',
            district='Almamya',
        )

        self.assertIs(result, village)
        self.assertEqual(mock_find.call_count, 4)
        self.assertEqual(mock_find.call_args_list[0].args, ('Conakry', 'R'))
        self.assertEqual(mock_find.call_args_list[3].args, ('Almamya', 'V'))
        self.assertEqual(mock_find.call_args_list[3].kwargs['parent'], ward)

    @patch('productive_inclusion.location_utils._find_location_by_name')
    def test_district_only(self, mock_find):
        village = MagicMock(name='V')
        mock_find.return_value = village
        result = resolve_village_by_admin_names(district='Almamya')
        self.assertIs(result, village)
        mock_find.assert_called_once_with('Almamya', 'V', parent=None)


class ResolveVillageForRowTests(SimpleTestCase):
    def setUp(self):
        self.service = SereImportService.__new__(SereImportService)

    @patch('productive_inclusion.services.resolve_village_by_admin_names')
    def test_prefers_hierarchy_over_village_id(self, mock_hierarchy):
        import pandas as pd

        village = MagicMock()
        village.name = 'Almamya'
        mock_hierarchy.return_value = village
        row = pd.Series({
            'region': 'Conakry',
            'prefecture': 'Kaloum',
            'sous_prefecture': 'Centre',
            'district': 'Almamya',
            'village_id': '999',
        })
        stats = {'warnings': []}

        loc, label = self.service._resolve_village_for_row(row, stats)

        self.assertIs(loc, village)
        self.assertEqual(label, 'Almamya')
        mock_hierarchy.assert_called_once()

    @patch('productive_inclusion.services.resolve_village_location')
    @patch('productive_inclusion.services.resolve_village_by_admin_names')
    def test_fallback_to_village_id(self, mock_hierarchy, mock_by_id):
        import pandas as pd

        mock_hierarchy.return_value = None
        village = MagicMock()
        village.name = 'Village-X'
        mock_by_id.return_value = village
        row = pd.Series({
            'region': 'Conakry',
            'prefecture': 'Kaloum',
            'sous_prefecture': 'Centre',
            'district': 'Inconnu',
            'village_id': '42',
        })
        stats = {'warnings': []}

        loc, label = self.service._resolve_village_for_row(row, stats)

        self.assertIs(loc, village)
        self.assertEqual(label, 'Village-X')
        self.assertTrue(any('introuvable' in w.lower() for w in stats['warnings']))

    @patch('productive_inclusion.services.resolve_village_location')
    def test_village_id_only(self, mock_by_id):
        import pandas as pd

        village = MagicMock()
        village.name = 'ById'
        mock_by_id.return_value = village
        row = pd.Series({'village_id': '15'})
        stats = {'warnings': []}

        loc, label = self.service._resolve_village_for_row(row, stats)

        self.assertIs(loc, village)
        self.assertEqual(label, 'ById')
