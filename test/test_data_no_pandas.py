from __future__ import annotations

"""
Integration test for data.py without hitting the real Eurostat API.
Uses mocked responses to test the refactored pandas-free implementation.
"""

import sys
from unittest.mock import MagicMock, patch

# Mock QGIS modules before importing our code
sys.modules['qgis'] = MagicMock()
sys.modules['qgis.core'] = MagicMock()
sys.modules['qgis.PyQt'] = MagicMock()
sys.modules['qgis.PyQt.QtCore'] = MagicMock()
sys.modules['qgis.PyQt.QtNetwork'] = MagicMock()
sys.modules['qgis.PyQt.QtWidgets'] = MagicMock()
sys.modules['qgis.PyQt.QtGui'] = MagicMock()

from eurostat_downloader.src.data import Database, Dataset
from eurostat_downloader.src.enums import Language


def test_database_toc():
    """Test Database TOC operations without pandas."""
    print('\n=== Testing Database TOC Operations ===')

    mock_toc_data = [
        {
            'title': 'Population by age and sex',
            'code': 'DEMO_POP',
            'type': 'dataset',
            'last update of data': '2024-01-15',
            'last table structure change': '2023-12-01',
            'data start': '2000',
            'data end': '2023',
        },
        {
            'title': 'GDP per capita',
            'code': 'GDP_PC',
            'type': 'dataset',
            'last update of data': '2024-01-10',
            'last table structure change': '2023-11-15',
            'data start': '1995',
            'data end': '2023',
        },
        {
            'title': 'Unemployment rate',
            'code': 'UNEMP_RATE',
            'type': 'dataset',
            'last update of data': '2024-01-20',
            'last table structure change': '2023-12-10',
            'data start': '2005',
            'data end': '2023',
        },
    ]

    with patch('src.data.eurostat.get_toc', return_value=mock_toc_data):
        db = Database(lang=Language.ENGLISH)
        db.initialize_toc()

        print('✓ Database initialized')
        print(f'  TOC size: {db.toc_size}')
        # Note: toc_size will be 3 entries × number of agencies that succeed
        assert db.toc_size >= 3, f'Expected at least 3, got {db.toc_size}'

        toc = db.toc
        print(f'✓ TOC retrieved: {len(toc)} entries')
        assert len(toc) >= 3

        titles = db.toc_titles
        print(f'✓ Titles extracted: {len(titles)} titles')
        assert 'Population by age and sex' in titles
        assert 'GDP per capita' in titles

        subset = db.get_subset('population')
        print(f'✓ Subset by keyword "population": {len(subset)} entries')
        assert len(subset) >= 1
        assert any(row['code'] == 'DEMO_POP' for row in subset)

        subset_empty = db.get_subset('nonexistent')
        print(f'✓ Subset with no matches: {len(subset_empty)} entries')
        assert len(subset_empty) == 0

        codes = db.get_codes()
        print(f'✓ Codes extracted: {len(codes)} codes')
        assert 'DEMO_POP' in codes
        assert 'GDP_PC' in codes

        print('✓ All Database tests passed!')


def test_dataset_operations():
    """Test Dataset operations without pandas."""
    print('\n=== Testing Dataset Operations ===')

    mock_toc_data = [
        {
            'title': 'Test Dataset',
            'code': 'TEST_DATA',
            'type': 'dataset',
            'last update of data': '2024-01-15',
            'last table structure change': '2023-12-01',
            'data start': '2020',
            'data end': '2023',
        }
    ]

    mock_data_response = {
        'columns': ['geo', 'sex\\TIME_PERIOD', '2020', '2021', '2022', '2023'],
        'data': [
            ['BE', 'T', '100', '105', '110', '115'],
            ['FR', 'T', '200', '210', '220', '230'],
            ['DE', 'T', '300', '315', '330', '345'],
        ],
    }

    with patch('src.data.eurostat.get_toc', return_value=mock_toc_data):
        db = Database(lang=Language.ENGLISH)
        db.initialize_toc()

        with patch('src.data.eurostat.get_pars', return_value=['geo', 'sex']):
            with patch(
                'src.data.eurostat.get_data', return_value=mock_data_response
            ):
                with patch('src.data.eurostat.get_dic', return_value=[]):
                    dataset = Dataset(db=db, code='TEST_DATA')
                    dataset.initialize_df()

                    print('✓ Dataset initialized')

                    title = dataset.title
                    print(f'✓ Title: {title}')
                    assert title == 'Test Dataset'

                    params = dataset.params
                    print(f'✓ Parameters: {params}')
                    assert params == ['geo', 'sex']

                    data = dataset.df
                    print(
                        f'✓ Data retrieved with {len(data["columns"])} columns'
                    )
                    assert len(data['columns']) == 6

                    # Check TIME_PERIOD was removed
                    assert 'sex' in data['columns'][1]
                    assert '\\TIME_PERIOD' not in data['columns'][1]
                    print('✓ TIME_PERIOD removed from column names')

                    date_cols = dataset.date_columns
                    print(f'✓ Date columns: {date_cols}')
                    assert date_cols == ['2020', '2021', '2022', '2023']

                    data_start = dataset.data_start
                    data_end = dataset.data_end
                    print(f'✓ Data range: {data_start} to {data_end}')
                    assert data_start == '2020'
                    assert data_end == '2023'

                    frequency = dataset.frequency
                    print(f'✓ Frequency: {frequency}')
                    assert frequency == 'BE'

                    print('✓ All Dataset tests passed!')


def test_caching():
    """Test TOC caching functionality."""
    print('\n=== Testing TOC Caching ===')

    import tempfile
    import json
    from pathlib import Path

    mock_toc_data = [
        {
            'title': 'Cache Test Dataset',
            'code': 'CACHE_TEST',
            'type': 'dataset',
            'last update of data': '2024-01-15',
            'last table structure change': '2023-12-01',
            'data start': '2020',
            'data end': '2023',
        }
    ]

    with tempfile.TemporaryDirectory() as tmpdir:
        cache_path = Path(tmpdir) / 'test_cache.json'

        with patch('src.data.eurostat.get_toc', return_value=mock_toc_data):
            db = Database(lang=Language.ENGLISH)
            db._cache_path = cache_path
            db.initialize_toc()

            db.cache_toc()
            print(f'✓ TOC cached to {cache_path}')
            assert cache_path.exists()

            with open(cache_path, 'r') as f:
                json.load(f)
            print('✓ Cache file readable')

            db2 = Database(lang=Language.ENGLISH)
            db2._cache_path = cache_path
            db2._load_toc_from_cache()
            print('✓ TOC loaded from cache')

            assert db2.toc_size >= 1
            assert any(row['code'] == 'CACHE_TEST' for row in db2.toc)
            print('✓ All caching tests passed!')


def test_get_subset_edge_cases():
    """Test edge cases in get_subset."""
    print('\n=== Testing Get Subset Edge Cases ===')

    mock_toc_data = [
        {
            'title': 'Population Data',
            'code': 'POP_DATA',
            'type': 'dataset',
            'last update of data': '2024-01-15',
            'last table structure change': '2023-12-01',
            'data start': '2020',
            'data end': '2023',
        }
    ]

    with patch('src.data.eurostat.get_toc', return_value=mock_toc_data):
        db = Database(lang=Language.ENGLISH)
        db.initialize_toc()

        # Test with empty keyword
        subset = db.get_subset('')
        print(f'✓ Empty keyword returns all: {len(subset)} entries')
        assert len(subset) >= 1

        # Test with whitespace
        subset = db.get_subset('   ')
        print(f'✓ Whitespace keyword returns all: {len(subset)} entries')
        assert len(subset) >= 1

        # Test case insensitive
        subset = db.get_subset('POPULATION')
        print(f'✓ Case insensitive search works: {len(subset)} entries')
        assert len(subset) >= 1

        # Test searching by code
        subset = db.get_subset('POP_DATA')
        print(f'✓ Search by code works: {len(subset)} entries')
        assert len(subset) >= 1

        print('✓ All edge case tests passed!')


if __name__ == '__main__':
    try:
        test_database_toc()
        test_dataset_operations()
        test_caching()
        test_get_subset_edge_cases()
        print('\n' + '=' * 50)
        print('🎉 ALL TESTS PASSED!')
        print('=' * 50)
    except AssertionError as e:
        print(f'\n❌ Test failed: {e}')
        sys.exit(1)
    except Exception as e:
        print(f'\n❌ Unexpected error: {e}')
        import traceback

        traceback.print_exc()
        sys.exit(1)
