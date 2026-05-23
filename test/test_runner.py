# coding=utf-8
"""
Comprehensive test runner for Eurostat Downloader QGIS Plugin.

This module runs all tests in the test suite and provides detailed reporting.
"""

__author__ = 'cuvuliucalexandrei@gmail.com'
__date__ = '2024-01-30'

import sys
import unittest
from pathlib import Path

# Add parent directory to path to import modules
TEST_DIR = Path(__file__).parent
sys.path.insert(0, str(TEST_DIR.parent))

from test.utilities import get_qgis_app

# Initialize QGIS application
QGIS_APP = get_qgis_app()

# Import all test modules
# Note: test_data and test_integration require pandas and are excluded
from test import (
    test_enums,
    test_init,
    test_qgis_environment,
    test_qgs_converter,
    test_resources,
    test_settings,
    test_toc_cache,
    test_translations,
    test_tree_database,
    test_ui_gisco,
    test_ui_loading_dialog,
    test_ui_main_dialog,
    test_ui_missing_modules,
    test_ui_parameters_dialog,
    test_ui_settings_dialog,
    test_ui_time_dialog,
    test_utils,
    test_workers,
    test_workflows,
)


def run_all_tests(verbosity=2):
    """
    Run all tests in the test suite.

    Args:
        verbosity (int): Level of output detail (0=quiet, 1=normal, 2=verbose)

    Returns:
        unittest.TestResult: Test results object
    """
    # Create test suite
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()

    # Add all test modules
    test_modules_list = [
        test_enums,
        test_init,
        test_qgis_environment,
        test_qgs_converter,
        test_resources,
        test_settings,
        test_toc_cache,
        test_translations,
        test_tree_database,
        test_ui_gisco,
        test_ui_loading_dialog,
        test_ui_main_dialog,
        test_ui_missing_modules,
        test_ui_parameters_dialog,
        test_ui_settings_dialog,
        test_ui_time_dialog,
        test_utils,
        test_workers,
        test_workflows,
    ]

    for module in test_modules_list:
        suite.addTests(loader.loadTestsFromModule(module))

    # Run tests
    runner = unittest.TextTestRunner(verbosity=verbosity)
    result = runner.run(suite)

    return result


def run_category_tests(category, verbosity=2):
    """
    Run tests for a specific category.

    Categories:
        - data: Data layer tests (Database, Dataset, GISCO)
        - gui: GUI component tests
        - integration: Integration and workflow tests
        - utils: Utility function tests
        - config: Configuration and settings tests
        - core: Core functionality (enums, init, resources)

    Args:
        category (str): Test category to run
        verbosity (int): Level of output detail

    Returns:
        unittest.TestResult: Test results object
    """
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()

    category_map = {
        'tree': [test_tree_database],
        'utils': [test_utils],
        'config': [test_settings],
        'core': [
            test_enums,
            test_init,
            test_resources,
            test_qgis_environment,
            test_translations,
        ],
        'ui': [
            test_ui_gisco,
            test_ui_loading_dialog,
            test_ui_main_dialog,
            test_ui_missing_modules,
            test_ui_parameters_dialog,
            test_ui_settings_dialog,
            test_ui_time_dialog,
        ],
    }

    if category not in category_map:
        print(f'Unknown category: {category}')
        print(f'Available categories: {", ".join(category_map.keys())}')
        return None

    for module in category_map[category]:
        suite.addTests(loader.loadTestsFromModule(module))

    runner = unittest.TextTestRunner(verbosity=verbosity)
    result = runner.run(suite)

    return result


def print_test_summary():
    """Print a summary of all available tests."""
    print('=' * 70)
    print('EUROSTAT DOWNLOADER QGIS PLUGIN - TEST SUITE')
    print('=' * 70)
    print()

    test_categories = {
        'Tree Structure Tests': [
            'test_tree_database.py - Tree widget hierarchy',
            '  - TOC hierarchy preservation',
            '  - Parent-child relationships',
            '  - Level transition validation',
        ],
        'Utility Tests': [
            'test_utils.py - Helper functions and widgets',
            '  - CheckableComboBox widget',
            '  - QComboboxCompleter widget',
            '  - Layer creation functions',
            '  - Table utilities',
        ],
        'Configuration Tests': [
            'test_settings.py - Settings and proxy configuration',
            '  - ProxySettings handling',
            '  - GlobalSettings initialization',
            '  - QGIS proxy detection',
        ],
        'Core Tests': [
            'test_enums.py - Enumeration types',
            'test_init.py - Plugin initialization',
            'test_resources.py - Resource loading',
            'test_qgis_environment.py - QGIS environment',
            'test_translations.py - Internationalization',
        ],
    }

    for category, tests in test_categories.items():
        print(f'\n{category}')
        print('-' * 70)
        for test in tests:
            print(f'  {test}')

    print('\n' + '=' * 70)
    print('Usage:')
    print('  python test_runner.py              # Run all tests')
    print(
        '  python test_runner.py tree         # Run tree structure tests only'
    )
    print('  python test_runner.py utils        # Run utility tests only')
    print('  python test_runner.py config       # Run config tests only')
    print('  python test_runner.py core         # Run core tests only')
    print('=' * 70)
    print()


def main():
    """Main entry point for test runner."""
    import argparse

    parser = argparse.ArgumentParser(
        description='Run tests for Eurostat Downloader QGIS Plugin'
    )
    parser.add_argument(
        'category',
        nargs='?',
        choices=['all', 'tree', 'utils', 'config', 'core', 'ui'],
        default='all',
        help='Category of tests to run (default: all)',
    )
    parser.add_argument(
        '-v',
        '--verbosity',
        type=int,
        choices=[0, 1, 2],
        default=2,
        help='Output verbosity (0=quiet, 1=normal, 2=verbose)',
    )
    parser.add_argument(
        '-s',
        '--summary',
        action='store_true',
        help='Print test summary and exit',
    )

    args = parser.parse_args()

    if args.summary:
        print_test_summary()
        return 0

    print_test_summary()
    print(f'\nRunning {args.category} tests...\n')

    if args.category == 'all':
        result = run_all_tests(verbosity=args.verbosity)
    else:
        result = run_category_tests(args.category, verbosity=args.verbosity)

    if result is None:
        return 1

    # Print summary
    print('\n' + '=' * 70)
    print('TEST SUMMARY')
    print('=' * 70)
    print(f'Tests run: {result.testsRun}')
    print(
        f'Successes: {result.testsRun - len(result.failures) - len(result.errors)}'
    )
    print(f'Failures: {len(result.failures)}')
    print(f'Errors: {len(result.errors)}')
    print(f'Skipped: {len(result.skipped)}')
    print('=' * 70)

    # Return appropriate exit code
    return 0 if result.wasSuccessful() else 1


if __name__ == '__main__':
    sys.exit(main())
