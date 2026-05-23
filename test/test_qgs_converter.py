# coding=utf-8
"""Tests for ``QgsConverter`` data-conversion helpers.

Regression coverage for the join-data path that surfaced
``AttributeError: type object 'QVariant' has no attribute 'Type'`` under PyQt6:
``QgsConverter.dtype_mapper`` returns Qt type enums that must use
``QMetaType.Type.*`` rather than the dropped ``QVariant.Type.*`` form.

All inputs are synthetic Python lists. No Eurostat/GISCO network calls.
"""

from __future__ import annotations

import unittest

from test.utilities import get_qgis_app

QGIS_APP, CANVAS, IFACE, PARENT = get_qgis_app()

from qgis.PyQt import QtCore  # noqa: E402

from eurostat_downloader.src.eurostat_downloader import QgsConverter  # noqa: E402


class TestDtypeMapper(unittest.TestCase):
    """``dtype_mapper`` returns a QMetaType.Type for any list of values."""

    def test_strings_become_qstring(self) -> None:
        self.assertEqual(
            QgsConverter.dtype_mapper(['A', 'B', 'C']),
            QtCore.QMetaType.Type.QString,
        )

    def test_integers_become_int(self) -> None:
        self.assertEqual(
            QgsConverter.dtype_mapper([1, 2, 3]),
            QtCore.QMetaType.Type.Int,
        )

    def test_floats_become_double(self) -> None:
        self.assertEqual(
            QgsConverter.dtype_mapper([1.5, 2.5, 3.0]),
            QtCore.QMetaType.Type.Double,
        )

    def test_bools_become_bool(self) -> None:
        self.assertEqual(
            QgsConverter.dtype_mapper([True, False, True]),
            QtCore.QMetaType.Type.Bool,
        )

    def test_numeric_strings_become_int(self) -> None:
        self.assertEqual(
            QgsConverter.dtype_mapper(['1', '2', '3']),
            QtCore.QMetaType.Type.Int,
        )

    def test_decimal_strings_become_double(self) -> None:
        self.assertEqual(
            QgsConverter.dtype_mapper(['1.5', '2.0', '3.14']),
            QtCore.QMetaType.Type.Double,
        )

    def test_all_none_becomes_qstring(self) -> None:
        self.assertEqual(
            QgsConverter.dtype_mapper([None, None, None]),
            QtCore.QMetaType.Type.QString,
        )

    def test_empty_list_becomes_qstring(self) -> None:
        self.assertEqual(
            QgsConverter.dtype_mapper([]),
            QtCore.QMetaType.Type.QString,
        )

    def test_leading_none_and_empty_are_skipped(self) -> None:
        self.assertEqual(
            QgsConverter.dtype_mapper([None, '', 42]),
            QtCore.QMetaType.Type.Int,
        )


if __name__ == '__main__':
    unittest.main()
