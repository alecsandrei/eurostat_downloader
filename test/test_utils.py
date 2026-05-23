# coding=utf-8
"""Tests for utils module - CheckableComboBox, layer functions, etc."""

from __future__ import annotations

__author__ = 'cuvuliucalexandrei@gmail.com'
__date__ = '2024-01-30'

import unittest
from qgis.core import (
    QgsFeature,
    Qgis,
    QgsGeometry,
    QgsPointXY,
)
from qgis.PyQt import QtCore, QtGui, QtWidgets

from eurostat_downloader.src.utils import (
    CheckableComboBox,
    QComboboxCompleter,
    layer_from_features,
    get_table_item,
    color_row,
)
from test.utilities import get_qgis_app

QGIS_APP = get_qgis_app()


class TestCheckableComboBox(unittest.TestCase):
    """Test CheckableComboBox custom widget."""

    def setUp(self) -> None:
        """Setup test fixtures."""
        self.app = QtWidgets.QApplication.instance()
        if self.app is None:
            self.app = QtWidgets.QApplication([])
        self.combo = CheckableComboBox()

    def test_initialization(self) -> None:
        """Test CheckableComboBox initializes correctly."""
        self.assertTrue(self.combo.isEditable())
        self.assertTrue(self.combo.lineEdit().isReadOnly())
        self.assertIsInstance(
            self.combo.itemDelegate(), CheckableComboBox.Delegate
        )

    def test_add_item(self) -> None:
        """Test adding items to combo box."""
        self.combo.addItem('Item 1')
        self.combo.addItem('Item 2', 'custom_data')

        self.assertEqual(self.combo.model().rowCount(), 2)
        self.assertEqual(self.combo.model().item(0).text(), 'Item 1')
        self.assertEqual(self.combo.model().item(1).text(), 'Item 2')
        self.assertEqual(self.combo.model().item(1).data(), 'custom_data')

    def test_add_items(self) -> None:
        """Test adding multiple items at once."""
        items = ['Item 1', 'Item 2', 'Item 3']
        self.combo.addItems(items)

        self.assertEqual(self.combo.model().rowCount(), 3)
        for i, item in enumerate(items):
            self.assertEqual(self.combo.model().item(i).text(), item)

    def test_check_state(self) -> None:
        """Test checking and unchecking items."""
        self.combo.addItems(['Item 1', 'Item 2', 'Item 3'])

        # Initially all unchecked
        for i in range(3):
            item = self.combo.model().item(i)
            self.assertEqual(item.checkState(), QtCore.Qt.CheckState.Unchecked)

        # Check first item
        self.combo.model().item(0).setCheckState(QtCore.Qt.CheckState.Checked)
        self.assertEqual(
            self.combo.model().item(0).checkState(),
            QtCore.Qt.CheckState.Checked,
        )

    def test_current_data(self) -> None:
        """Test getting checked items data."""
        self.combo.addItems(['Item 1', 'Item 2', 'Item 3'])

        # Check items 0 and 2
        self.combo.model().item(0).setCheckState(QtCore.Qt.CheckState.Checked)
        self.combo.model().item(2).setCheckState(QtCore.Qt.CheckState.Checked)

        data = self.combo.currentData()
        self.assertEqual(len(data), 2)
        self.assertIn('Item 1', data)
        self.assertIn('Item 3', data)

    def test_deselect_items(self) -> None:
        """Test deselecting all items."""
        self.combo.addItems(['Item 1', 'Item 2'])

        # Check both items
        self.combo.model().item(0).setCheckState(QtCore.Qt.CheckState.Checked)
        self.combo.model().item(1).setCheckState(QtCore.Qt.CheckState.Checked)

        # Deselect all
        self.combo.deselect_items()

        for i in range(2):
            self.assertEqual(
                self.combo.model().item(i).checkState(),
                QtCore.Qt.CheckState.Unchecked,
            )

    def test_update_text(self) -> None:
        """Test text updates when items are checked."""
        self.combo.addItems(['Item 1', 'Item 2', 'Item 3'])

        # Check items
        self.combo.model().item(0).setCheckState(QtCore.Qt.CheckState.Checked)
        self.combo.model().item(1).setCheckState(QtCore.Qt.CheckState.Checked)

        self.combo.updateText()
        text = self.combo.lineEdit().text()

        # Text should contain Item 1 at least (may be elided)
        self.assertIn('Item 1', text)


class TestQComboboxCompleter(unittest.TestCase):
    """Test QComboboxCompleter custom widget."""

    def setUp(self) -> None:
        """Setup test fixtures."""
        self.app = QtWidgets.QApplication.instance()
        if self.app is None:
            self.app = QtWidgets.QApplication([])
        self.parent = QtWidgets.QWidget()
        self.combo = QComboboxCompleter(self.parent)

    def test_initialization(self) -> None:
        """Test QComboboxCompleter initializes correctly."""
        self.assertTrue(self.combo.isEditable())
        self.assertEqual(
            self.combo.insertPolicy(), QtWidgets.QComboBox.InsertPolicy.NoInsert
        )
        self.assertEqual(
            self.combo.completer().completionMode(),
            QtWidgets.QCompleter.CompletionMode.PopupCompletion,
        )


class TestLayerFromFeatures(unittest.TestCase):
    """Test layer_from_features function."""

    def setUp(self) -> None:
        """Setup test fixtures."""
        pass

    def test_polygon_layer(self) -> None:
        """Test creating polygon layer from features."""
        # Create mock polygon feature
        feature = QgsFeature()
        geometry = QgsGeometry.fromWkt('POLYGON((0 0, 1 0, 1 1, 0 1, 0 0))')
        feature.setGeometry(geometry)

        layer = layer_from_features([feature], crs='4326')

        self.assertIsNotNone(layer)
        self.assertTrue(layer.isValid())
        self.assertEqual(layer.geometryType(), Qgis.GeometryType.Polygon)
        self.assertEqual(layer.crs().authid(), 'EPSG:4326')

    def test_point_layer(self) -> None:
        """Test creating point layer from features."""
        feature = QgsFeature()
        geometry = QgsGeometry.fromPointXY(QgsPointXY(0, 0))
        feature.setGeometry(geometry)

        layer = layer_from_features([feature], crs='4326')

        self.assertIsNotNone(layer)
        self.assertTrue(layer.isValid())
        self.assertEqual(layer.geometryType(), Qgis.GeometryType.Point)

    def test_line_layer(self) -> None:
        """Test creating line layer from features."""
        feature = QgsFeature()
        geometry = QgsGeometry.fromWkt('LINESTRING(0 0, 1 1, 2 2)')
        feature.setGeometry(geometry)

        layer = layer_from_features([feature], crs='4326')

        self.assertIsNotNone(layer)
        self.assertTrue(layer.isValid())
        self.assertEqual(layer.geometryType(), Qgis.GeometryType.Line)


class TestGetTableItem(unittest.TestCase):
    """Test get_table_item function."""

    def test_get_table_item_string(self) -> None:
        """Test creating table item from string."""
        item = get_table_item('Test Value')

        self.assertEqual(item.text(), 'Test Value')
        self.assertTrue(item.flags() & QtCore.Qt.ItemFlag.ItemIsSelectable)
        self.assertTrue(item.flags() & QtCore.Qt.ItemFlag.ItemIsEnabled)
        self.assertFalse(item.flags() & QtCore.Qt.ItemFlag.ItemIsEditable)

    def test_get_table_item_number(self) -> None:
        """Test creating table item from number."""
        item = get_table_item(42)

        self.assertEqual(item.text(), '42')

    def test_get_table_item_alignment(self) -> None:
        """Test table item is center-aligned."""
        item = get_table_item('Test')

        self.assertTrue(item.textAlignment() & QtCore.Qt.AlignmentFlag.AlignCenter)


class TestColorRow(unittest.TestCase):
    """Test color_row function."""

    def setUp(self) -> None:
        """Setup test fixtures."""
        self.app = QtWidgets.QApplication.instance()
        if self.app is None:
            self.app = QtWidgets.QApplication([])
        self.table = QtWidgets.QTableWidget(3, 3)

    def test_color_row(self) -> None:
        """Test coloring a table row."""
        # Add items to table
        for col in range(3):
            self.table.setItem(
                0, col, QtWidgets.QTableWidgetItem(f'Item {col}')
            )

        # Color the row
        test_color = QtGui.QColor(255, 0, 0)
        color_row(self.table, 0, test_color)

        # Check all items in row are colored
        for col in range(3):
            item = self.table.item(0, col)
            self.assertEqual(item.background().color(), test_color)

    def test_color_empty_row(self) -> None:
        """Test coloring a row with no items."""
        test_color = QtGui.QColor(0, 255, 0)
        color_row(self.table, 1, test_color)

        # Items should be created and colored
        for col in range(3):
            item = self.table.item(1, col)
            self.assertIsNotNone(item)
            self.assertEqual(item.background().color(), test_color)


if __name__ == '__main__':
    suite = unittest.TestLoader().loadTestsFromModule(__import__(__name__))
    runner = unittest.TextTestRunner(verbosity=2)
    runner.run(suite)
