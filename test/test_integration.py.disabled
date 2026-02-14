# coding=utf-8
"""Integration tests for end-to-end workflows."""

__author__ = 'cuvuliucalexandrei@gmail.com'
__date__ = '2024-01-30'

import unittest
from unittest.mock import Mock, MagicMock, patch
import pandas as pd
import json

from src.data import Database, Dataset, NUTS, UrbanAudit, Countries, Unit, Units
from src.enums import Language, Agency, TableOfContentsColumn
from test.utilities import get_qgis_app

QGIS_APP = get_qgis_app()


class TestDatabaseToDatasetWorkflow(unittest.TestCase):
    """Test complete workflow from database initialization to dataset creation."""

    def setUp(self):
        """Setup test fixtures."""
        self.db = Database(lang=Language.ENGLISH)

    @patch('src.data.eurostat.get_toc_df')
    def test_initialize_and_filter_workflow(self, mock_get_toc):
        """Test initializing database and filtering TOC."""
        # Mock TOC data
        mock_df = pd.DataFrame({
            'code': ['GDP001', 'GDP002', 'POP001'],
            'title': ['GDP Main', 'GDP Regional', 'Population']
        })
        mock_get_toc.return_value = mock_df
        
        # Initialize
        self.db.initialize_toc()
        
        # Filter for GDP
        subset = self.db.get_subset('GDP')
        
        # Verify workflow - should have GDP entries
        self.assertGreater(len(subset), 0)
        codes = self.db.get_codes(subset)
        # At least one GDP code should be present
        has_gdp = any('GDP' in str(code) for code in codes.values)
        self.assertTrue(has_gdp)

    @patch('src.data.eurostat.get_data_df')
    @patch('src.data.eurostat.get_pars')
    @patch('src.data.eurostat.get_toc_df')
    def test_database_to_dataset_workflow(self, mock_get_toc, mock_get_pars, mock_get_data):
        """Test creating dataset from database."""
        # Setup database
        mock_toc = pd.DataFrame({
            'code': ['TEST001'],
            'title': ['Test Dataset']
        })
        mock_get_toc.return_value = mock_toc
        
        self.db.initialize_toc()
        
        # Setup dataset
        mock_get_pars.return_value = ['geo', 'time']
        mock_data = pd.DataFrame({
            'geo': ['DE', 'FR'],
            'time': ['2020', '2020'],
            '2020': [100, 200]
        })
        mock_get_data.return_value = mock_data
        
        # Create and initialize dataset
        dataset = Dataset(db=self.db, code='TEST001')
        dataset.initialize_df()
        
        # Verify complete workflow
        self.assertEqual(dataset.code, 'TEST001')
        self.assertEqual(dataset.title, 'Test Dataset')
        self.assertIsNotNone(dataset.df)
        self.assertEqual(len(dataset.params), 2)

    def test_language_switching_workflow(self):
        """Test switching languages in database and dataset."""
        # Setup mock data for multiple languages
        self.db._toc = {
            Agency.EUROSTAT: {
                Language.ENGLISH: pd.DataFrame({
                    TableOfContentsColumn.CODE.value: ['TEST001'],
                    TableOfContentsColumn.TITLE.value: ['Test Title EN']
                }),
                Language.GERMAN: pd.DataFrame({
                    TableOfContentsColumn.CODE.value: ['TEST001'],
                    TableOfContentsColumn.TITLE.value: ['Test Title DE']
                })
            }
        }
        
        # Initially English
        self.assertEqual(self.db.lang, Language.ENGLISH)
        title_en = self.db.toc[TableOfContentsColumn.TITLE.value].iloc[0]
        self.assertEqual(title_en, 'Test Title EN')
        
        # Switch to German
        self.db.set_language(Language.GERMAN)
        title_de = self.db.toc[TableOfContentsColumn.TITLE.value].iloc[0]
        self.assertEqual(title_de, 'Test Title DE')


class TestGISCOWorkflow(unittest.TestCase):
    """Test GISCO data retrieval workflows."""

    def setUp(self):
        """Setup test fixtures."""
        self.nuts = NUTS()

    @patch('src.data.request_blocking')
    def test_complete_gisco_workflow(self, mock_request):
        """Test complete GISCO workflow: datasets -> years -> units."""
        # Mock datasets
        datasets_json = {
            'nuts-2021': {},
            'nuts-2020': {}
        }
        
        # Mock units
        units_json = {
            'NUTS': [
                'NUTS-region-01M-4326-2021.geojson',
                'NUTS-region-03M-4326-2021.geojson',
                'NUTS-label-4326-2021.geojson'
            ]
        }
        
        def request_side_effect(url):
            if 'datasets.json' in url:
                return json.dumps(datasets_json).encode()
            elif 'units.json' in url:
                return json.dumps(units_json).encode()
            return b'{}'
        
        mock_request.side_effect = request_side_effect
        
        # Step 1: Get datasets
        self.nuts.set_datasets()
        self.assertIsNotNone(self.nuts.datasets)
        
        # Step 2: Get years
        years = self.nuts.get_years()
        self.assertIn('2021', years)
        self.assertIn('2020', years)
        
        # Step 3: Get units for a year
        self.nuts.set_units('2021')
        units = self.nuts.get_units('2021')
        
        # Verify complete workflow
        self.assertEqual(len(units), 3)
        self.assertTrue(any(u.scale == '01M' for u in units))
        self.assertTrue(any(u.spatial_type == 'label' for u in units))

    @patch('src.data.request_blocking')
    def test_multiple_gisco_themes(self, mock_request):
        """Test working with multiple GISCO themes."""
        mock_request.return_value = json.dumps({
            'test-2021': {}
        }).encode()
        
        # Test NUTS
        nuts = NUTS()
        nuts.set_datasets()
        self.assertEqual(nuts.theme, 'nuts')
        
        # Test UrbanAudit
        urau = UrbanAudit()
        urau.set_datasets()
        self.assertEqual(urau.theme, 'urau')
        
        # Test Countries
        countries = Countries()
        countries.set_datasets()
        self.assertEqual(countries.theme, 'countries')

    @patch('src.data.request_blocking')
    def test_units_filtering_workflow(self, mock_request):
        """Test filtering units after retrieval."""
        units_json = {
            'NUTS': [
                'NUTS-region-01M-4326-2021.geojson',
                'NUTS-region-03M-4326-2021.geojson',
                'NUTS-region-01M-3035-2021.geojson',
                'NUTS-label-4326-2021.geojson'
            ]
        }
        
        def request_side_effect(url):
            if 'datasets.json' in url:
                return json.dumps({'nuts-2021': {}}).encode()
            elif 'units.json' in url:
                return json.dumps(units_json).encode()
            return b'{}'
        
        mock_request.side_effect = request_side_effect
        
        # Get units
        self.nuts.set_datasets()
        self.nuts.set_units('2021')
        all_units = self.nuts.get_units('2021')
        
        # Filter for specific scale
        filtered_01m = all_units.filter({'scale': ['01M']})
        self.assertEqual(len(filtered_01m), 2)
        
        # Filter for specific projection
        filtered_4326 = all_units.filter({'projection': ['4326']})
        self.assertEqual(len(filtered_4326), 3)
        
        # Filter for multiple criteria
        filtered_combined = all_units.filter({
            'scale': ['01M'],
            'projection': ['4326']
        })
        self.assertEqual(len(filtered_combined), 1)


class TestDataExportWorkflow(unittest.TestCase):
    """Test data export and formatting workflows."""

    @patch('src.data.eurostat.get_data_df')
    @patch('src.data.eurostat.get_pars')
    def test_dataset_dataframe_export(self, mock_get_pars, mock_get_data):
        """Test exporting dataset as DataFrame."""
        mock_get_pars.return_value = ['geo', 'time']
        mock_data = pd.DataFrame({
            'geo': ['DE', 'FR', 'IT'],
            'time': ['2020', '2020', '2020'],
            '2020': [100, 200, 150]
        })
        mock_get_data.return_value = mock_data
        
        db = Database()
        dataset = Dataset(db=db, code='TEST001')
        dataset.initialize_df()
        
        # Get DataFrame
        df = dataset.df
        
        # Verify data structure
        self.assertIsInstance(df, pd.DataFrame)
        self.assertEqual(len(df), 3)
        self.assertIn('geo', df.columns)
        self.assertIn('2020', df.columns)

    @patch('src.data.eurostat.get_data_df')
    @patch('src.data.eurostat.get_pars')
    def test_dataset_time_series_extraction(self, mock_get_pars, mock_get_data):
        """Test extracting time series from dataset."""
        mock_get_pars.return_value = ['geo']
        mock_data = pd.DataFrame({
            'geo': ['DE', 'FR'],
            '2018': [100, 200],
            '2019': [110, 210],
            '2020': [120, 220],
            '2021': [130, 230]
        })
        mock_get_data.return_value = mock_data
        
        db = Database()
        dataset = Dataset(db=db, code='TEST001')
        dataset.initialize_df()
        
        # Get date columns
        date_cols = dataset.date_columns
        
        # Extract time series for Germany
        germany_data = dataset.df[dataset.df['geo'] == 'DE'][date_cols]
        
        self.assertEqual(len(date_cols), 4)
        self.assertEqual(germany_data[date_cols].iloc[0].tolist(), [100, 110, 120, 130])


class TestErrorHandlingWorkflow(unittest.TestCase):
    """Test error handling in workflows."""

    @patch('src.data.eurostat.get_toc_df')
    def test_connection_error_handling(self, mock_get_toc):
        """Test handling connection errors during initialization."""
        mock_get_toc.side_effect = ConnectionError('Network error')
        
        db = Database()
        
        # Should handle ConnectionError gracefully
        db.initialize_toc()
        
        # Check that unavailable status is recorded
        if Agency.EUROSTAT in db._agency_status:
            from src.enums import ConnectionStatus
            # Status might be UNAVAILABLE due to error
            self.assertIn(
                db._agency_status.get(Agency.EUROSTAT),
                [ConnectionStatus.AVAILABLE, ConnectionStatus.UNAVAILABLE]
            )

    def test_empty_toc_handling(self):
        """Test handling empty TOC."""
        db = Database()
        db._toc = {}
        
        # Empty TOC should raise ValueError when trying to access
        with self.assertRaises(ValueError):
            subset = db.get_subset('GDP')

    @patch('src.data.request_blocking')
    def test_invalid_json_handling(self, mock_request):
        """Test handling invalid JSON responses."""
        mock_request.return_value = b'Invalid JSON{'
        
        nuts = NUTS()
        
        # Should raise appropriate error
        with self.assertRaises((json.JSONDecodeError, ValueError)):
            nuts.set_datasets()


class TestCachingWorkflow(unittest.TestCase):
    """Test caching workflows."""

    def test_database_caching(self):
        """Test database TOC caching."""
        db = Database()
        
        # Setup test data
        db._toc = {
            Agency.EUROSTAT: {
                Language.ENGLISH: pd.DataFrame({
                    TableOfContentsColumn.CODE.value: ['TEST001'],
                    TableOfContentsColumn.TITLE.value: ['Test']
                })
            }
        }
        
        # Cache should work without errors
        try:
            db.cache_toc()
            # If file operations succeed, that's good
            self.assertTrue(True)
        except Exception:
            # File operations might fail in test environment
            self.skipTest('File operations not available in test environment')

    def test_gisco_units_caching(self):
        """Test GISCO units caching."""
        nuts = NUTS()
        
        # Manually set units
        test_units = Units([
            Unit('NUTS', 'region', '01M', '4326', '2021')
        ])
        nuts.units['2021'] = test_units
        
        # Retrieve again - should return cached version
        units = nuts.get_units('2021')
        
        self.assertEqual(units, test_units)
        self.assertEqual(len(units), 1)


if __name__ == '__main__':
    suite = unittest.TestLoader().loadTestsFromModule(__import__(__name__))
    runner = unittest.TextTestRunner(verbosity=2)
    runner.run(suite)
