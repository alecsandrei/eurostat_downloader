from __future__ import annotations

import unittest
from test.utilities import get_qgis_app

QGIS_APP = get_qgis_app()

from eurostat_downloader.src.data import Database
from eurostat_downloader.src.enums import Language, Agency


class TestTreeDatabase(unittest.TestCase):
    """Test the tree database structure."""

    def test_toc_hierarchy_preserved(self):
        """Test that TOC maintains hierarchical order, not sorted by level."""
        # Create a database and mock TOC data
        db = Database()

        # Simulate hierarchical TOC data (as returned by API)
        mock_toc_eurostat = [
            {'code': 'A', 'title': 'Category A', 'level': 0, 'type': 'folder'},
            {
                'code': 'A1',
                'title': 'Subcategory A1',
                'level': 1,
                'type': 'folder',
            },
            {
                'code': 'A1a',
                'title': 'Dataset A1a',
                'level': 2,
                'type': 'dataset',
            },
            {
                'code': 'A2',
                'title': 'Subcategory A2',
                'level': 1,
                'type': 'folder',
            },
            {'code': 'B', 'title': 'Category B', 'level': 0, 'type': 'folder'},
            {
                'code': 'B1',
                'title': 'Dataset B1',
                'level': 1,
                'type': 'dataset',
            },
        ]

        # Manually set TOC to avoid network calls
        db._toc = {Agency.EUROSTAT: {Language.ENGLISH: mock_toc_eurostat}}

        # Get TOC
        toc = db.toc

        # Verify hierarchy is preserved (children follow parents)
        codes = [item['code'] for item in toc]

        # A1 should come after A
        self.assertLess(codes.index('A'), codes.index('A1'))
        # A1a should come after A1
        self.assertLess(codes.index('A1'), codes.index('A1a'))
        # A2 should come after A1a (sibling of A1)
        self.assertLess(codes.index('A1a'), codes.index('A2'))
        # B should come after all A children
        self.assertLess(codes.index('A2'), codes.index('B'))
        # B1 should come after B
        self.assertLess(codes.index('B'), codes.index('B1'))

        # Verify no level jumps > 1
        for i in range(1, len(toc)):
            prev_level = toc[i - 1]['level']
            curr_level = toc[i]['level']
            # Level can increase by at most 1, or decrease by any amount
            if curr_level > prev_level:
                self.assertLessEqual(
                    curr_level - prev_level,
                    1,
                    f'Invalid level jump from {prev_level} to {curr_level}',
                )


if __name__ == '__main__':
    unittest.main()
