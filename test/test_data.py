# coding=utf-8
"""Tests for data module - Database, Dataset, GISCO classes."""

__author__ = 'cuvuliucalexandrei@gmail.com'
__date__ = '2024-01-30'

import unittest
from unittest.mock import Mock, patch, MagicMock
import pandas as pd
import json

from src.data import (
    Database, Dataset, Unit, Units, NUTS, UrbanAudit, Countries,
    request_blocking, request
)
from src.enums import Language, Agency, TableOfContentsColumn, ConnectionStatus
from test.utilities import get_qgis_app

QGIS_APP = get_qgis_app()


class TestDatabase(unittest.TestCase):
    """Test Database class functionality."""

    def setUp(self):
        """Setup test fixtures."""
        self.db = Database(lang=Language.ENGLISH)

    def test_database_initialization(self):
        """Test database initializes with correct defaults."""
        self.assertEqual(self.db.lang, Language.ENGLISH)
        self.assertIsNotNone(self.db._cache_path)
        self.assertTrue(self.db._cache_path.parent.exists())

    def test_set_language(self):
        """Test language can be changed."""
        self.db.set_language(Language.FRENCH)
        self.assertEqual(self.db.lang, Language.FRENCH)

    @patch('src.data.eurostat.get_toc_df')
    def test_initialize_toc(self, mock_get_toc):
        """Test TOC initialization."""
        mock_df = pd.DataFrame({
            'code': ['TEST001'],
            'title': ['Test Dataset']
        })
        mock_get_toc.return_value = mock_df
        
        self.db.initialize_toc()
        
        self.assertGreater(len(self.db._toc), 0)

    def test_get_subset(self):
        """Test filtering TOC by keyword."""
        # Create mock TOC
        self.db._toc = {
            Agency.EUROSTAT: {
                Language.ENGLISH: pd.DataFrame({
                    TableOfContentsColumn.CODE.value: ['GDP001', 'POP001', 'GDP002'],
                    TableOfContentsColumn.TITLE.value: ['GDP Data', 'Population', 'GDP Regional']
                })
            }
        }
        
        subset = self.db.get_subset('GDP')
        self.assertEqual(len(subset), 2)
        
        # Empty keyword should return all
        subset_all = self.db.get_subset('')
        self.assertEqual(len(subset_all), 3)

    def test_get_titles(self):
        """Test extracting titles from TOC."""
        self.db._toc = {
            Agency.EUROSTAT: {
                Language.ENGLISH: pd.DataFrame({
                    TableOfContentsColumn.CODE.value: ['TEST001'],
                    TableOfContentsColumn.TITLE.value: ['Test Title']
                })
            }
        }
        
        titles = self.db.get_titles()
        self.assertEqual(len(titles), 1)
        self.assertEqual(titles.iloc[0], 'Test Title')

    def test_get_codes(self):
        """Test extracting codes from TOC."""
        self.db._toc = {
            Agency.EUROSTAT: {
                Language.ENGLISH: pd.DataFrame({
                    TableOfContentsColumn.CODE.value: ['TEST001'],
                    TableOfContentsColumn.TITLE.value: ['Test Title']
                })
            }
        }
        
        codes = self.db.get_codes()
        self.assertEqual(len(codes), 1)
        self.assertEqual(codes.iloc[0], 'TEST001')


class TestDataset(unittest.TestCase):
    """Test Dataset class functionality."""

    def setUp(self):
        """Setup test fixtures."""
        self.db = Database(lang=Language.ENGLISH)
        self.dataset = Dataset(db=self.db, code='TEST001')

    def test_dataset_initialization(self):
        """Test dataset initializes correctly."""
        self.assertEqual(self.dataset.code, 'TEST001')
        self.assertEqual(self.dataset.db, self.db)

    def test_set_language(self):
        """Test dataset language can be changed."""
        self.dataset.set_language(Language.GERMAN)
        self.assertEqual(self.dataset.lang, Language.GERMAN)

    @patch('src.data.eurostat.get_data_df')
    @patch('src.data.eurostat.get_pars')
    def test_initialize_df(self, mock_get_pars, mock_get_data):
        """Test dataset dataframe initialization."""
        mock_get_pars.return_value = ['geo', 'time']
        mock_df = pd.DataFrame({
            'geo': ['DE', 'FR'],
            'time': ['2020', '2020'],
            '2020': [100, 200]
        })
        mock_get_data.return_value = mock_df
        
        self.dataset.initialize_df()
        
        self.assertIsNotNone(self.dataset._df)

    def test_remove_time_period_str(self):
        """Test TIME_PERIOD string is removed from columns."""
        df = pd.DataFrame(columns=['geo', r'\TIME_PERIOD2020', r'\TIME_PERIOD2021'])
        Dataset.remove_time_period_str(df)
        
        self.assertIn('geo', df.columns)
        self.assertIn('2020', df.columns)
        self.assertIn('2021', df.columns)


class TestUnit(unittest.TestCase):
    """Test Unit class functionality."""

    def test_unit_from_filename(self):
        """Test creating Unit from filename."""
        filename = 'NUTS-region-01M-4326-2021.geojson'
        unit = Unit.from_filename(filename)
        
        self.assertEqual(unit.id, 'NUTS')
        self.assertEqual(unit.spatial_type, 'region')
        self.assertEqual(unit.scale, '01M')
        self.assertEqual(unit.projection, '4326')
        self.assertEqual(unit.year, '2021')

    def test_unit_from_filename_label(self):
        """Test creating Unit from label filename (no scale)."""
        filename = 'NUTS-label-4326-2021.geojson'
        unit = Unit.from_filename(filename)
        
        self.assertEqual(unit.id, 'NUTS')
        self.assertEqual(unit.spatial_type, 'label')
        self.assertIsNone(unit.scale)
        self.assertEqual(unit.projection, '4326')
        self.assertEqual(unit.year, '2021')

    def test_unit_to_filename(self):
        """Test converting Unit back to filename."""
        unit = Unit('NUTS', 'region', '01M', '4326', '2021')
        filename = unit.to_filename()
        
        self.assertEqual(filename, 'NUTS-region-01M-4326-2021.geojson')

    def test_unit_getitem(self):
        """Test accessing Unit fields by name."""
        unit = Unit('NUTS', 'region', '01M', '4326', '2021')
        
        self.assertEqual(unit['id'], 'NUTS')
        self.assertEqual(unit['scale'], '01M')


class TestUnits(unittest.TestCase):
    """Test Units collection class."""

    def setUp(self):
        """Setup test fixtures."""
        self.units = Units([
            Unit('NUTS', 'region', '01M', '4326', '2021'),
            Unit('NUTS', 'region', '03M', '4326', '2021'),
            Unit('NUTS', 'label', None, '4326', '2021'),
        ])

    def test_units_from_json(self):
        """Test creating Units from JSON."""
        json_data = {
            'NUTS': [
                'NUTS-region-01M-4326-2021.geojson',
                'NUTS-label-4326-2021.geojson'
            ]
        }
        
        units = Units.from_json(json_data)
        self.assertEqual(len(units), 2)

    def test_units_as_dicts(self):
        """Test converting Units to list of dicts."""
        dicts = self.units.as_dicts()
        
        self.assertEqual(len(dicts), 3)
        self.assertIsInstance(dicts[0], dict)
        self.assertEqual(dicts[0]['id'], 'NUTS')

    def test_get_unique_field_values(self):
        """Test getting unique values for fields."""
        unique = self.units.get_unique_field_values(['scale', 'spatial_type'])
        
        self.assertIn('01M', unique['scale'])
        self.assertIn('03M', unique['scale'])
        self.assertIn('region', unique['spatial_type'])
        self.assertIn('label', unique['spatial_type'])

    def test_filter_units(self):
        """Test filtering units."""
        filtered = self.units.filter({'scale': ['01M']})
        self.assertEqual(len(filtered), 1)
        self.assertEqual(filtered[0].scale, '01M')
        
        # Test with empty filter (should include None values)
        filtered_none = self.units.filter({'scale': []})
        self.assertEqual(len(filtered_none), 3)


class TestGISCO(unittest.TestCase):
    """Test GISCO classes."""

    def setUp(self):
        """Setup test fixtures."""
        self.nuts = NUTS()
        self.urau = UrbanAudit()
        self.countries = Countries()

    def test_nuts_theme(self):
        """Test NUTS theme property."""
        self.assertEqual(self.nuts.theme, 'nuts')

    def test_urban_audit_theme(self):
        """Test UrbanAudit theme property."""
        self.assertEqual(self.urau.theme, 'urau')

    def test_countries_theme(self):
        """Test Countries theme property."""
        self.assertEqual(self.countries.theme, 'countries')

    @patch('src.data.request_blocking')
    def test_set_datasets(self, mock_request):
        """Test setting datasets."""
        mock_request.return_value = json.dumps({
            'nuts-2021': {},
            'nuts-2020': {}
        }).encode()
        
        self.nuts.set_datasets()
        
        self.assertIsNotNone(self.nuts.datasets)
        self.assertEqual(len(self.nuts.datasets), 2)

    @patch('src.data.request_blocking')
    def test_get_years(self, mock_request):
        """Test getting available years."""
        mock_request.return_value = json.dumps({
            'nuts-2021': {},
            'nuts-2020': {},
            'nuts-2019': {}
        }).encode()
        
        years = self.nuts.get_years()
        
        self.assertEqual(years, ['2019', '2020', '2021'])

    @patch('src.data.request_blocking')
    def test_set_units(self, mock_request):
        """Test setting units for a year."""
        mock_json = {
            'NUTS': ['NUTS-region-01M-4326-2021.geojson']
        }
        mock_request.return_value = json.dumps(mock_json).encode()
        
        self.nuts.set_units('2021')
        
        self.assertIn('2021', self.nuts.units)
        self.assertEqual(len(self.nuts.units['2021']), 1)


class TestRequestFunctions(unittest.TestCase):
    """Test network request functions."""

    @patch('src.data.QgsNetworkAccessManager')
    def test_request_blocking(self, mock_manager):
        """Test blocking request."""
        mock_reply = Mock()
        mock_reply.content().data.return_value = b'test data'
        
        with patch('src.data.GLOBAL_SETTINGS.network_manager.blockingGet', return_value=mock_reply):
            result = request_blocking('http://test.com')
            self.assertEqual(result, b'test data')

    @patch('src.data.QgsNetworkAccessManager')
    def test_request(self, mock_manager):
        """Test async request."""
        mock_mgr = Mock()
        mock_reply = Mock()
        mock_mgr.get.return_value = mock_reply
        
        result = request('http://test.com', manager=mock_mgr)
        
        self.assertEqual(result, mock_reply)
        mock_mgr.get.assert_called_once()


class TestDatabaseAdvanced(unittest.TestCase):
    """Advanced Database tests."""

    def setUp(self):
        """Setup test fixtures."""
        self.db = Database(lang=Language.ENGLISH)

    def test_cache_path_creation(self):
        """Test cache path is created correctly."""
        self.assertIsNotNone(self.db._cache_path)
        self.assertTrue(self.db._cache_path.parent.exists())
        self.assertIn('eurostat_toc', str(self.db._cache_path))

    def test_toc_property(self):
        """Test TOC property returns correct DataFrame."""
        self.db._toc = {
            Agency.EUROSTAT: {
                Language.ENGLISH: pd.DataFrame({
                    TableOfContentsColumn.CODE.value: ['TEST001'],
                    TableOfContentsColumn.TITLE.value: ['Test Title']
                })
            }
        }
        
        toc = self.db.toc
        self.assertIsInstance(toc, pd.DataFrame)
        self.assertGreater(len(toc), 0)

    def test_toc_size(self):
        """Test getting TOC size."""
        self.db._toc = {
            Agency.EUROSTAT: {
                Language.ENGLISH: pd.DataFrame({
                    TableOfContentsColumn.CODE.value: ['A', 'B', 'C'],
                    TableOfContentsColumn.TITLE.value: ['T1', 'T2', 'T3']
                })
            }
        }
        
        self.assertEqual(self.db.toc_size, 3)

    def test_toc_titles_property(self):
        """Test getting TOC titles property."""
        self.db._toc = {
            Agency.EUROSTAT: {
                Language.ENGLISH: pd.DataFrame({
                    TableOfContentsColumn.CODE.value: ['TEST001'],
                    TableOfContentsColumn.TITLE.value: ['Test Title']
                })
            }
        }
        
        titles = self.db.toc_titles
        self.assertIsInstance(titles, pd.Series)
        self.assertEqual(titles.iloc[0], 'Test Title')

    @patch('src.data.eurostat.get_toc_df')
    def test_initialize_toc_multiple_agencies(self, mock_get_toc):
        """Test TOC initialization for multiple agencies."""
        mock_df = pd.DataFrame({
            'code': ['TEST001', 'TEST002'],
            'title': ['Title 1', 'Title 2']
        })
        mock_get_toc.return_value = mock_df
        
        self.db.initialize_toc()
        
        # Should have entries for agencies that were queried
        self.assertGreater(len(self.db._toc), 0)

    def test_get_subset_case_insensitive(self):
        """Test filtering is case insensitive."""
        self.db._toc = {
            Agency.EUROSTAT: {
                Language.ENGLISH: pd.DataFrame({
                    TableOfContentsColumn.CODE.value: ['GDP001'],
                    TableOfContentsColumn.TITLE.value: ['Gross Domestic Product']
                })
            }
        }
        
        subset_upper = self.db.get_subset('GDP')
        subset_lower = self.db.get_subset('gdp')
        
        self.assertEqual(len(subset_upper), len(subset_lower))

    def test_get_codes_with_subset(self):
        """Test getting codes from a subset."""
        subset = pd.DataFrame({
            TableOfContentsColumn.CODE.value: ['CODE1', 'CODE2'],
            TableOfContentsColumn.TITLE.value: ['Title1', 'Title2']
        })
        
        codes = self.db.get_codes(subset)
        self.assertEqual(len(codes), 2)
        self.assertIn('CODE1', codes.values)


class TestDatasetAdvanced(unittest.TestCase):
    """Advanced Dataset tests."""

    def setUp(self):
        """Setup test fixtures."""
        self.db = Database(lang=Language.ENGLISH)
        self.db._toc = {
            Agency.EUROSTAT: {
                Language.ENGLISH: pd.DataFrame({
                    TableOfContentsColumn.CODE.value: ['TEST001'],
                    TableOfContentsColumn.TITLE.value: ['Test Dataset']
                })
            }
        }
        self.dataset = Dataset(db=self.db, code='TEST001')

    def test_title_property(self):
        """Test getting dataset title."""
        title = self.dataset.title
        self.assertEqual(title, 'Test Dataset')

    @patch('src.data.eurostat.get_data_df')
    @patch('src.data.eurostat.get_pars')
    def test_params_property(self, mock_get_pars, mock_get_data):
        """Test getting dataset parameters."""
        mock_get_pars.return_value = ['geo', 'time', 'unit']
        mock_df = pd.DataFrame({
            'geo': ['DE'],
            'time': ['2020'],
            'unit': ['EUR'],
            '2020': [100]
        })
        mock_get_data.return_value = mock_df
        
        self.dataset.initialize_df()
        
        self.assertEqual(len(self.dataset.params), 3)
        self.assertIn('geo', self.dataset.params)

    @patch('src.data.eurostat.get_data_df')
    @patch('src.data.eurostat.get_pars')
    def test_date_columns(self, mock_get_pars, mock_get_data):
        """Test getting date columns from dataset."""
        mock_get_pars.return_value = ['geo']
        mock_df = pd.DataFrame({
            'geo': ['DE', 'FR'],
            '2019': [100, 200],
            '2020': [110, 210],
            '2021': [120, 220]
        })
        mock_get_data.return_value = mock_df
        
        self.dataset.initialize_df()
        
        date_cols = self.dataset.date_columns
        self.assertEqual(len(date_cols), 3)
        self.assertIn('2019', date_cols)
        self.assertIn('2021', date_cols)

    @patch('src.data.eurostat.get_data_df')
    @patch('src.data.eurostat.get_pars')
    def test_data_start_end(self, mock_get_pars, mock_get_data):
        """Test getting data start and end dates."""
        mock_get_pars.return_value = ['geo']
        mock_df = pd.DataFrame({
            'geo': ['DE'],
            '2018': [100],
            '2019': [110],
            '2020': [120]
        })
        mock_get_data.return_value = mock_df
        
        self.dataset.initialize_df()
        
        self.assertEqual(self.dataset.data_start, '2018')
        self.assertEqual(self.dataset.data_end, '2020')

    @patch('src.data.eurostat.get_data_df')
    @patch('src.data.eurostat.get_pars')
    @patch('src.data.eurostat.get_dic')
    def test_params_info(self, mock_get_dic, mock_get_pars, mock_get_data):
        """Test getting parameter information."""
        mock_get_pars.return_value = ['geo']
        mock_get_data.return_value = pd.DataFrame({
            'geo': ['DE'],
            '2020': [100]
        })
        mock_get_dic.return_value = [('DE', 'Germany')]
        
        self.dataset.initialize_df()
        
        self.assertIsInstance(self.dataset.params_info, dict)

    def test_remove_time_period_multiple_columns(self):
        """Test removing TIME_PERIOD from multiple columns."""
        df = pd.DataFrame(columns=[
            'geo',
            r'\TIME_PERIOD2019',
            r'\TIME_PERIOD2020',
            r'\TIME_PERIOD2021'
        ])
        
        Dataset.remove_time_period_str(df)
        
        self.assertIn('2019', df.columns)
        self.assertIn('2020', df.columns)
        self.assertIn('2021', df.columns)
        self.assertNotIn(r'\TIME_PERIOD2019', df.columns)


class TestUnitsAdvanced(unittest.TestCase):
    """Advanced Units tests."""

    def test_units_iteration(self):
        """Test iterating over units."""
        units = Units([
            Unit('NUTS', 'region', '01M', '4326', '2021'),
            Unit('NUTS', 'region', '03M', '4326', '2021'),
        ])
        
        count = 0
        for unit in units:
            count += 1
            self.assertIsInstance(unit, Unit)
        
        self.assertEqual(count, 2)

    def test_units_indexing(self):
        """Test accessing units by index."""
        unit1 = Unit('NUTS', 'region', '01M', '4326', '2021')
        unit2 = Unit('NUTS', 'region', '03M', '4326', '2021')
        units = Units([unit1, unit2])
        
        self.assertEqual(units[0], unit1)
        self.assertEqual(units[1], unit2)

    def test_units_length(self):
        """Test getting units length."""
        units = Units([
            Unit('NUTS', 'region', '01M', '4326', '2021'),
            Unit('NUTS', 'region', '03M', '4326', '2021'),
        ])
        
        self.assertEqual(len(units), 2)

    def test_filter_multiple_fields(self):
        """Test filtering by multiple fields."""
        units = Units([
            Unit('NUTS', 'region', '01M', '4326', '2021'),
            Unit('NUTS', 'region', '03M', '4326', '2021'),
            Unit('NUTS', 'label', None, '4326', '2021'),
            Unit('NUTS', 'region', '01M', '3035', '2021'),
        ])
        
        filtered = units.filter({
            'scale': ['01M'],
            'projection': ['4326']
        })
        
        self.assertEqual(len(filtered), 1)
        self.assertEqual(filtered[0].scale, '01M')
        self.assertEqual(filtered[0].projection, '4326')

    def test_get_unique_all_fields(self):
        """Test getting unique values for all fields."""
        units = Units([
            Unit('NUTS', 'region', '01M', '4326', '2021'),
            Unit('URAU', 'region', '03M', '3035', '2020'),
        ])
        
        unique = units.get_unique_field_values()
        
        self.assertIn('id', unique)
        self.assertIn('NUTS', unique['id'])
        self.assertIn('URAU', unique['id'])


class TestGISCOAdvanced(unittest.TestCase):
    """Advanced GISCO tests."""

    def setUp(self):
        """Setup test fixtures."""
        self.nuts = NUTS()

    @patch('src.data.request_blocking')
    def test_set_datasets_parsing(self, mock_request):
        """Test dataset parsing from JSON."""
        mock_request.return_value = json.dumps({
            'nuts-2021': {'description': 'NUTS 2021 dataset'},
            'nuts-2020': {'description': 'NUTS 2020 dataset'}
        }).encode()
        
        self.nuts.set_datasets()
        
        self.assertIsNotNone(self.nuts.datasets)
        self.assertIn('nuts-2021', self.nuts.datasets)
        self.assertIn('nuts-2020', self.nuts.datasets)

    @patch('src.data.request_blocking')
    def test_get_years_ordering(self, mock_request):
        """Test years are returned."""
        mock_request.return_value = json.dumps({
            'nuts-2019': {},
            'nuts-2021': {},
            'nuts-2020': {}
        }).encode()
        
        years = self.nuts.get_years()
        
        # Should contain all years (order depends on JSON parsing)
        self.assertEqual(set(years), {'2021', '2020', '2019'})

    @patch('src.data.request_blocking')
    def test_set_units_multiple_types(self, mock_request):
        """Test setting units with multiple types."""
        mock_json = {
            'NUTS': [
                'NUTS-region-01M-4326-2021.geojson',
                'NUTS-region-03M-4326-2021.geojson',
                'NUTS-label-4326-2021.geojson'
            ]
        }
        mock_request.return_value = json.dumps(mock_json).encode()
        
        self.nuts.set_units('2021')
        
        self.assertIn('2021', self.nuts.units)
        self.assertEqual(len(self.nuts.units['2021']), 3)

    def test_get_units_caching(self):
        """Test units are cached after first retrieval."""
        self.nuts.units['2021'] = Units([
            Unit('NUTS', 'region', '01M', '4326', '2021')
        ])
        
        # Should return cached units without making request
        units = self.nuts.get_units('2021')
        
        self.assertEqual(len(units), 1)

    @patch('src.data.request')
    def test_get_feature_from_unit(self, mock_request):
        """Test getting feature from unit."""
        unit = Unit('NUTS', 'region', '01M', '4326', '2021')
        mock_reply = Mock()
        mock_request.return_value = mock_reply
        
        reply = self.nuts.get_feature_from_unit(unit)
        
        self.assertEqual(reply, mock_reply)
        mock_request.assert_called_once()


if __name__ == '__main__':
    suite = unittest.TestLoader().loadTestsFromModule(__import__(__name__))
    runner = unittest.TextTestRunner(verbosity=2)
    runner.run(suite)
