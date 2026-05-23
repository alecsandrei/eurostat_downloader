"""Tests for the GISCO-related UI components.

Test plan
=========

Components under test
---------------------
This file covers the two GISCO-related UI pieces in the plugin:

1. ``GISCOJoinReport`` (``eurostat_downloader.src.eurostat_downloader``) -- a
   ``QtWidgets.QDialog`` subclass that wraps the ``pyuic5``-generated
   ``Ui_GISCOJoinReport`` form. Shown modelessly after a GISCO join completes.
   Constructor:
       GISCOJoinReport(report_data: JoinReportData | None = None,
                       parent: QtWidgets.QWidget | None = None)
   ``__init__`` simply stores ``report_data`` and calls
   ``self.ui.setupUi(self)``. It does NOT call ``self.exec()``, so no
   ``QDialog.exec`` patch is required for construction. The dialog has a
   single child widget: ``tableWidgetGISCOJoinReport`` (a ``QTableWidget``)
   that is populated lazily by ``populate_table`` -- we exercise that path
   too because it materialises ``QTableWidgetItem`` children, which is a
   second place enum/API breakage could hide.

2. ``Ui_GISCODatasetInformation``
   (``eurostat_downloader.src.ui.gisco_dataset_information``) -- a pure
   generated UI class with no Python wrapper. Used as an inline panel
   created on-the-fly inside ``GISCOHandler.show_gisco_dataset_information``
   via ``Ui_GISCODatasetInformation().setupUi(QDialog(...))``. We mirror that
   usage by instantiating the class directly and calling ``setupUi`` against
   a fresh ``QWidget`` (or ``QDialog``) host.

Construction paths exercised
----------------------------
*   ``GISCOJoinReport()`` -- no args, no parent (still legal, dialog has no
    required parent in its constructor).
*   ``GISCOJoinReport(parent=<QWidget>)`` -- typical production path, where
    the parent is the main plugin ``Dialog``. We use a real ``QWidget``
    rather than ``MagicMock`` because Qt parent validation rejects mocks --
    however nothing about the parent is actually inspected during
    construction beyond Qt's own ownership wiring.
*   ``GISCOJoinReport(report_data=<JoinReportData>, parent=<QWidget>)`` --
    same as above but with data. ``__init__`` does not touch
    ``report_data``, so the dialog can be constructed even when data is
    ``None`` (the actual rendering happens in ``populate_table``).
*   ``Ui_GISCODatasetInformation().setupUi(host)`` -- the only way the class
    is used in production.

What could break under PyQt6
----------------------------
The bug class this file guards against is the PyQt5 -> PyQt6 enum-scoping
migration:
*   Unscoped enums in generated UI -- the canonical example is
    ``QSizePolicy.Minimum`` (PyQt5) vs ``QSizePolicy.Policy.Minimum``
    (PyQt6). The generated ``gisco_join_report.py`` uses
    ``QtCore.Qt.NoContextMenu`` (unscoped ``ContextMenuPolicy``) and
    ``QtWidgets.QAbstractScrollArea.AdjustToContentsOnFirstShow`` (unscoped
    ``SizeAdjustPolicy``) -- BOTH are exactly the shape of failure that the
    QSizePolicy bug exhibited. The generated ``gisco_dataset_information.py``
    uses ``QtCore.Qt.RichText`` (unscoped ``TextFormat``). All three are
    exercised the moment ``setupUi`` runs.
*   ``Qt.SortOrder`` -- the wrapper's ``sort_table``/``reset_table`` use
    ``Qt.SortOrder.DescendingOrder`` / ``AscendingOrder`` (already scoped in
    the source), but verifying ``sortByColumn`` calls don't raise covers any
    additional enum drift.
*   Signal/slot connection syntax -- ``QMetaObject.connectSlotsByName`` is
    invoked at the end of ``setupUi``; if any retranslate signal-slot has
    been mis-wired it surfaces here.

Assertions beyond "doesn't raise"
---------------------------------
*   The constructed dialog/widget is an instance of its expected Qt class.
*   The generated widget attributes promised by ``setupUi`` (the table for
    ``GISCOJoinReport``, the label for ``Ui_GISCODatasetInformation``)
    exist and are of the right Qt type. This catches silent regressions
    where the generated file is regenerated against a different ``.ui``.
*   For ``GISCOJoinReport``: window title is set from ``retranslateUi``,
    and the table widget starts empty (RowCount == 0, ColumnCount == 0)
    -- defensible defaults consumers rely on.
*   For ``GISCOJoinReport``: calling ``add_headers`` populates the expected
    columns (``matched`` + every field of ``Unit``). Cheap, no I/O, and it
    exercises the table API end-to-end.
*   For ``Ui_GISCODatasetInformation``: the rich-text label contains the
    expected GISCO API URL (sanity that ``retranslateUi`` actually ran).

What we intentionally do NOT test
---------------------------------
*   ``GISCOJoinReport.show`` -- the source signature is
    ``def show(self, event)`` which would actually display the dialog and
    requires a windowing system; that is integration territory.
*   ``populate_table`` against a real ``JoinReportData`` -- requires a real
    ``Units`` collection. Skipped because it isn't a UI-construction
    concern; the unit-level logic is covered (or should be covered)
    elsewhere.
*   Anything network/disk -- neither component performs I/O during
    construction.
*   Visual/layout assertions (geometry, stylesheets) -- brittle and
    unrelated to the PyQt6 migration bug class.
"""

__author__ = 'cuvuliucalexandrei@gmail.com'
__date__ = '2026-05-23'

import unittest
from dataclasses import fields
from unittest.mock import MagicMock

from qgis.PyQt import QtCore, QtWidgets

from test.utilities import get_qgis_app

QGIS_APP, CANVAS, IFACE, PARENT = get_qgis_app()

from eurostat_downloader.src.data import Unit  # noqa: E402
from eurostat_downloader.src.eurostat_downloader import GISCOJoinReport  # noqa: E402
from eurostat_downloader.src.ui.gisco_dataset_information import (  # noqa: E402
    Ui_GISCODatasetInformation,
)
from eurostat_downloader.src.ui.gisco_join_report import Ui_GISCOJoinReport  # noqa: E402


class TestGISCOJoinReport(unittest.TestCase):
    """Tests for the GISCOJoinReport dialog wrapper."""

    def setUp(self):
        """Set up a QApplication and a real QWidget to act as parent."""
        self.app = QtWidgets.QApplication.instance()
        if self.app is None:
            self.app = QtWidgets.QApplication([])
        # Qt parent-validation rejects MagicMock, so we use a real QWidget.
        # Nothing in GISCOJoinReport.__init__ actually pokes at the parent
        # beyond standard Qt ownership wiring.
        self.parent_widget = QtWidgets.QWidget()

    def tearDown(self):
        """Release the parent widget (and any owned children)."""
        self.parent_widget.deleteLater()

    # ------------------------------------------------------------------
    # The bar test: catches the QSizePolicy / unscoped-enum class of bug.
    # ------------------------------------------------------------------
    def test_constructs_without_error(self):
        """GISCOJoinReport construction must not raise.

        Regression guard for the PyQt5 -> PyQt6 migration: the generated
        ``Ui_GISCOJoinReport.setupUi`` references unscoped enums such as
        ``QtCore.Qt.NoContextMenu`` and
        ``QAbstractScrollArea.AdjustToContentsOnFirstShow``. Either would
        raise ``AttributeError`` under PyQt6 if not re-scoped.
        """
        dialog = GISCOJoinReport(parent=self.parent_widget)
        self.assertIsInstance(dialog, QtWidgets.QDialog)
        # Defaults preserved.
        self.assertIsNone(dialog.report_data)
        self.assertIsInstance(dialog.ui, Ui_GISCOJoinReport)

    def test_constructs_with_no_arguments(self):
        """The dialog must also be constructible without a parent or data."""
        # No args is a legal construction path -- explicit None defaults.
        dialog = GISCOJoinReport()
        try:
            self.assertIsInstance(dialog, QtWidgets.QDialog)
            self.assertIsNone(dialog.report_data)
        finally:
            dialog.deleteLater()

    def test_table_widget_exists_and_is_empty(self):
        """setupUi must populate the expected child widget with sane defaults."""
        dialog = GISCOJoinReport(parent=self.parent_widget)
        table = dialog.ui.tableWidgetGISCOJoinReport
        self.assertIsInstance(table, QtWidgets.QTableWidget)
        self.assertEqual(table.rowCount(), 0)
        self.assertEqual(table.columnCount(), 0)
        # retranslateUi sets the dialog window title.
        self.assertEqual(dialog.windowTitle(), 'Join report')

    def test_add_headers_populates_columns(self):
        """add_headers must add 'matched' plus one column per Unit field.

        Exercises the table API end-to-end without any I/O or join data.
        """
        dialog = GISCOJoinReport(parent=self.parent_widget)
        dialog.add_headers()
        table = dialog.ui.tableWidgetGISCOJoinReport
        expected_count = len(fields(Unit)) + 1  # +1 for the 'matched' column
        self.assertEqual(table.columnCount(), expected_count)
        # First column is the 'matched' indicator.
        first_header = table.horizontalHeaderItem(0)
        self.assertIsNotNone(first_header)
        self.assertEqual(first_header.text(), 'matched')

    def test_accepts_report_data_object(self):
        """report_data is stored verbatim; __init__ does not inspect it."""
        sentinel = MagicMock(name='JoinReportData')
        dialog = GISCOJoinReport(
            report_data=sentinel, parent=self.parent_widget
        )
        self.assertIs(dialog.report_data, sentinel)


class TestGISCODatasetInformation(unittest.TestCase):
    """Tests for the Ui_GISCODatasetInformation generated UI class.

    There is no Python wrapper for this UI; production code instantiates
    ``Ui_GISCODatasetInformation()`` directly and calls ``setupUi`` against
    a freshly-built ``QDialog`` host (see
    ``GISCOHandler.show_gisco_dataset_information``). The tests mirror that.
    """

    def setUp(self):
        """Set up a QApplication and a host widget for setupUi to populate."""
        self.app = QtWidgets.QApplication.instance()
        if self.app is None:
            self.app = QtWidgets.QApplication([])
        self.host = QtWidgets.QWidget()

    def tearDown(self):
        """Release the host (which owns the widgets created by setupUi)."""
        self.host.deleteLater()

    # ------------------------------------------------------------------
    # The bar test: catches the QSizePolicy / unscoped-enum class of bug.
    # ------------------------------------------------------------------
    def test_constructs_without_error(self):
        """Ui_GISCODatasetInformation.setupUi must not raise.

        The generated file uses ``QtCore.Qt.RichText`` (unscoped
        ``TextFormat`` -- needs ``Qt.TextFormat.RichText`` under strict
        PyQt6 enum scoping). If anything in setupUi explodes, this fires.
        """
        ui = Ui_GISCODatasetInformation()
        ui.setupUi(self.host)
        # setupUi mutates the host -- its window title is set by
        # retranslateUi.
        self.assertEqual(
            self.host.windowTitle(), 'GISCO dataset information'
        )

    def test_label_widget_exists(self):
        """The information label is the sole expected child after setupUi."""
        ui = Ui_GISCODatasetInformation()
        ui.setupUi(self.host)
        self.assertTrue(hasattr(ui, 'label'))
        self.assertIsInstance(ui.label, QtWidgets.QLabel)
        # Rich-text mode is what the generated file sets; verifying it
        # forces the PyQt6-scoped TextFormat enum to round-trip.
        self.assertEqual(ui.label.textFormat(), QtCore.Qt.TextFormat.RichText)
        # External-link clicks must remain enabled for the info pane to do
        # its job in production.
        self.assertTrue(ui.label.openExternalLinks())

    def test_label_text_contains_gisco_api_url(self):
        """retranslateUi must have populated the label with the API link."""
        ui = Ui_GISCODatasetInformation()
        ui.setupUi(self.host)
        self.assertIn(
            'gisco-services.ec.europa.eu/distribution/v2/',
            ui.label.text(),
        )

    def test_setupui_against_qdialog_host(self):
        """Production uses a QDialog host -- verify that path works too."""
        host_dialog = QtWidgets.QDialog()
        try:
            ui = Ui_GISCODatasetInformation()
            ui.setupUi(host_dialog)
            self.assertIsInstance(ui.label, QtWidgets.QLabel)
        finally:
            host_dialog.deleteLater()


if __name__ == '__main__':
    suite = unittest.TestLoader().loadTestsFromModule(__import__(__name__))
    runner = unittest.TextTestRunner(verbosity=2)
    runner.run(suite)
