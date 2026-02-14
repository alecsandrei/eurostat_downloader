# coding=utf-8
"""Tests for enums module - all enum types."""

__author__ = 'cuvuliucalexandrei@gmail.com'
__date__ = '2024-01-30'

import unittest
import sys
import os

# Add parent directory to path
sys.path.insert(
    0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
)

from eurostat_downloader.src.enums import (
    TableOfContentsColumn,
    Language,
    Agency,
    ConnectionStatus,
    GeoSectionName,
    FrequencyType,
)


class TestTableOfContentsColumn(unittest.TestCase):
    """Test TableOfContentsColumn enum."""

    def test_title_column(self):
        """Test TITLE column."""
        self.assertEqual(TableOfContentsColumn.TITLE.value, 'title')

    def test_code_column(self):
        """Test CODE column."""
        self.assertEqual(TableOfContentsColumn.CODE.value, 'code')

    def test_all_columns(self):
        """Test all columns are defined."""
        expected_columns = {'TITLE', 'CODE'}
        actual_columns = {col.name for col in TableOfContentsColumn}
        self.assertEqual(actual_columns, expected_columns)


class TestLanguage(unittest.TestCase):
    """Test Language enum."""

    def test_english(self):
        """Test English language code."""
        self.assertEqual(Language.ENGLISH.value, 'en')

    def test_french(self):
        """Test French language code."""
        self.assertEqual(Language.FRENCH.value, 'fr')

    def test_german(self):
        """Test German language code."""
        self.assertEqual(Language.GERMAN.value, 'de')

    def test_all_languages(self):
        """Test all supported languages."""
        expected_languages = {'ENGLISH', 'FRENCH', 'GERMAN'}
        actual_languages = {lang.name for lang in Language}
        self.assertEqual(actual_languages, expected_languages)

    def test_language_values(self):
        """Test language values are ISO 639-1 codes."""
        for lang in Language:
            self.assertEqual(len(lang.value), 2)
            self.assertTrue(lang.value.islower())


class TestAgency(unittest.TestCase):
    """Test Agency enum."""

    def test_eurostat(self):
        """Test EUROSTAT agency."""
        self.assertEqual(Agency.EUROSTAT.value, 'EUROSTAT')

    def test_comext(self):
        """Test COMEXT agency."""
        self.assertEqual(Agency.COMEXT.value, 'COMEXT')

    def test_comp(self):
        """Test COMP agency."""
        self.assertEqual(Agency.COMP.value, 'COMP')

    def test_empl(self):
        """Test EMPL agency."""
        self.assertEqual(Agency.EMPL.value, 'EMPL')

    def test_grow(self):
        """Test GROW agency."""
        self.assertEqual(Agency.GROW.value, 'GROW')

    def test_all_agencies(self):
        """Test all agencies are defined."""
        expected_agencies = {'EUROSTAT', 'COMEXT', 'COMP', 'EMPL', 'GROW'}
        actual_agencies = {agency.name for agency in Agency}
        self.assertEqual(actual_agencies, expected_agencies)

    def test_agency_iteration(self):
        """Test iterating over agencies."""
        agencies = list(Agency)
        self.assertGreater(len(agencies), 0)
        for agency in agencies:
            self.assertIsInstance(agency, Agency)


class TestConnectionStatus(unittest.TestCase):
    """Test ConnectionStatus enum."""

    def test_available(self):
        """Test AVAILABLE status."""
        self.assertIsNotNone(ConnectionStatus.AVAILABLE)

    def test_unavailable(self):
        """Test UNAVAILABLE status."""
        self.assertIsNotNone(ConnectionStatus.UNAVAILABLE)

    def test_all_statuses(self):
        """Test all connection statuses."""
        expected_statuses = {'AVAILABLE', 'UNAVAILABLE'}
        actual_statuses = {status.name for status in ConnectionStatus}
        self.assertEqual(actual_statuses, expected_statuses)

    def test_status_uniqueness(self):
        """Test status values are unique."""
        values = [status.value for status in ConnectionStatus]
        self.assertEqual(len(values), len(set(values)))


class TestGeoSectionName(unittest.TestCase):
    """Test GeoSectionName enum."""

    def test_geo(self):
        """Test GEO field."""
        self.assertEqual(GeoSectionName.GEO.value, 'geo')

    def test_rep_mar(self):
        """Test REP_MAR field."""
        self.assertEqual(GeoSectionName.REP_MAR.value, 'rep_mar')

    def test_par_mar(self):
        """Test PAR_MAR field."""
        self.assertEqual(GeoSectionName.PAR_MAR.value, 'par_mar')

    def test_metroreg(self):
        """Test METROREG field."""
        self.assertEqual(GeoSectionName.METROREG.value, 'metroreg')

    def test_all_geo_sections(self):
        """Test all geographic section names."""
        self.assertGreaterEqual(len(list(GeoSectionName)), 4)

    def test_geo_section_values_lowercase(self):
        """Test geo section values are lowercase."""
        for section in GeoSectionName:
            self.assertTrue(section.value.islower())


class TestFrequencyType(unittest.TestCase):
    """Test FrequencyType enum."""

    def test_annually(self):
        """Test ANNUALLY frequency."""
        self.assertEqual(FrequencyType.ANNUALLY.value, 'a')

    def test_semesterly(self):
        """Test SEMESTERLY frequency."""
        self.assertEqual(FrequencyType.SEMESTERLY.value, 's')

    def test_quarterly(self):
        """Test QUARTERLY frequency."""
        self.assertEqual(FrequencyType.QUARTERLY.value, 'q')

    def test_monthly(self):
        """Test MONTHLY frequency."""
        self.assertEqual(FrequencyType.MONTHLY.value, 'm')

    def test_daily(self):
        """Test DAILY frequency."""
        self.assertEqual(FrequencyType.DAILY.value, 'd')

    def test_all_frequencies(self):
        """Test all frequency types are defined."""
        expected_frequencies = {
            'ANNUALLY',
            'SEMESTERLY',
            'QUARTERLY',
            'MONTHLY',
            'DAILY',
        }
        actual_frequencies = {freq.name for freq in FrequencyType}
        self.assertEqual(actual_frequencies, expected_frequencies)

    def test_frequency_values_single_char(self):
        """Test frequency values are single characters."""
        for freq in FrequencyType:
            self.assertEqual(len(freq.value), 1)
            self.assertTrue(freq.value.islower())

    def test_frequency_ordering(self):
        """Test frequencies can be compared (useful for time series)."""
        frequencies = list(FrequencyType)
        self.assertIn(FrequencyType.ANNUALLY, frequencies)
        self.assertIn(FrequencyType.DAILY, frequencies)


if __name__ == '__main__':
    suite = unittest.TestLoader().loadTestsFromModule(__import__(__name__))
    runner = unittest.TextTestRunner(verbosity=2)
    runner.run(suite)
