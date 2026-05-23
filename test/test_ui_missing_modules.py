# coding=utf-8
"""Tests for the Missing Modules dialog UI (Ui_MissingModulesDialog).

What MissingModulesDialog is for
--------------------------------
This dialog is shown to the user when the Eurostat Downloader plugin starts
up and detects that one or more required Python packages are missing from
the QGIS Python environment. It exposes a tabbed UI listing the missing
modules and their states, an option to let the plugin install them via pip,
an option to handle them manually, and a tab containing the install logs.

What construction paths exist
-----------------------------
A grep across ``eurostat_downloader/`` shows that no Python wrapper class
(e.g. ``MissingModulesDialog(QDialog, Ui_MissingModulesDialog)``) currently
exists for this UI -- only the pyuic-generated ``Ui_MissingModulesDialog``
in ``eurostat_downloader/src/ui/missing_modules.py``. So the only relevant
construction path is the raw one:

    ui = Ui_MissingModulesDialog()
    dialog = QtWidgets.QDialog()
    ui.setupUi(dialog)

If a wrapper is later added, these tests would still catch the underlying
``setupUi`` regressions because the wrapper would call ``setupUi(self)``
internally.

What could break under PyQt6 specifically
-----------------------------------------
The plugin was just migrated from PyQt5 to PyQt6. The ``.py`` files in
``src/ui/`` were originally produced by ``pyuic5`` and use *unscoped*
enums such as ``QtCore.Qt.AlignCenter``, ``QtCore.Qt.LeftToRight``,
``QtCore.Qt.ElideRight``, and ``QtWidgets.QSizePolicy.Minimum``. Under
PyQt6, enums are strictly scoped: those attributes only exist on the
nested enum types (``Qt.AlignmentFlag.AlignCenter``,
``Qt.LayoutDirection.LeftToRight``, ``Qt.TextElideMode.ElideRight``,
``QSizePolicy.Policy.Minimum``). If ``setupUi`` ever hits an unscoped
form on PyQt6, it raises ``AttributeError`` at construction time, which
the existing unit tests never exercise.

For ``missing_modules.py`` specifically, the at-risk lines are the
``setAlignment(QtCore.Qt.AlignCenter)`` calls on the labels, the
``setLayoutDirection(QtCore.Qt.LeftToRight)`` on the table widget, and
``setTextElideMode(QtCore.Qt.ElideRight)``. Simply running ``setupUi``
on a real ``QDialog`` is enough to catch those.

Assertions valuable beyond "doesn't raise"
------------------------------------------
* The widgets the rest of the plugin will look up by attribute name are
  actually present (``pushButtonInstall``, ``pushButtonLetUserInstall``,
  ``tableWidgetModules``, ``tabWidgetMain``, ``pushButtonExportLogs``,
  ``labelLogs``, ``labelProcessFinished``).
* The translated strings used in the warning -- in particular the
  word "WARNING" in ``label_2`` and the dialog window title --
  survived ``retranslateUi``.
* The module table is configured with the four expected columns
  (Name / Version required / Version found / State).
* The tab widget has the two expected tabs and starts on the first.

What I chose NOT to test and why
--------------------------------
* No screenshot or visual rendering tests -- those would be brittle and
  out of scope for catching the PyQt6 enum-scoping bug class.
* No tests of click handlers / signal wiring -- there is no wrapper class
  yet, so there is nothing application-level to verify.
* No tests for resource imports beyond what ``setupUi`` itself triggers,
  since ``resources`` is imported defensively with try/except.
* No re-test of every label's exact translated text -- one representative
  assertion (the "WARNING" label and the window title) is enough to
  prove ``retranslateUi`` ran. Asserting every string would just couple
  the tests to translation churn.
"""

from __future__ import annotations

__author__ = 'cuvuliucalexandrei@gmail.com'
__date__ = '2026-05-23'

import unittest

from qgis.PyQt import QtWidgets

from eurostat_downloader.src.ui.missing_modules import Ui_MissingModulesDialog
from test.utilities import get_qgis_app

QGIS_APP, CANVAS, IFACE, PARENT = get_qgis_app()


class TestMissingModulesDialog(unittest.TestCase):
    """Test the pyuic-generated Ui_MissingModulesDialog under PyQt6."""

    def setUp(self) -> None:
        """Setup test fixtures.

        Ensures a QApplication exists and builds a fresh QDialog + Ui pair
        for each test. ``setupUi`` is where the PyQt5->PyQt6 enum bug
        class actually surfaces, so we run it here.
        """
        self.app = QtWidgets.QApplication.instance()
        if self.app is None:
            self.app = QtWidgets.QApplication([])

        self.dialog = QtWidgets.QDialog()
        self.ui = Ui_MissingModulesDialog()

    def tearDown(self) -> None:
        """Release the dialog so Qt can clean up between tests."""
        self.dialog.deleteLater()
        self.dialog = None
        self.ui = None  # type: ignore[assignment]

    def test_constructs_without_error(self) -> None:
        """``setupUi`` must run cleanly under PyQt6.

        This is the minimum bar: the bug we are guarding against
        (``AttributeError: type object 'QSizePolicy' has no attribute
        'Minimum'`` and similar unscoped-enum errors from pyuic5 output)
        manifests during ``setupUi``. If this test passes, the generated
        UI is at least syntactically compatible with the installed Qt
        bindings.
        """
        try:
            self.ui.setupUi(self.dialog)  # type: ignore[no-untyped-call]
        except AttributeError as exc:
            self.fail(
                'Ui_MissingModulesDialog.setupUi raised AttributeError '
                '(likely an unscoped PyQt5 enum under PyQt6): %s' % exc
            )

        # Sanity-check the dialog identity that setupUi assigned.
        self.assertEqual(self.dialog.objectName(), 'MissingModulesDialog')

    def test_expected_widgets_are_present(self) -> None:
        """The widgets the rest of the plugin relies on must exist.

        Asserting attribute presence catches the case where ``setupUi``
        silently no-ops past a broken section, and also locks in the
        public-ish surface other modules will key off of by name.
        """
        self.ui.setupUi(self.dialog)  # type: ignore[no-untyped-call]

        self.assertIsInstance(
            self.ui.pushButtonInstall, QtWidgets.QPushButton
        )
        self.assertIsInstance(
            self.ui.pushButtonLetUserInstall, QtWidgets.QPushButton
        )
        self.assertIsInstance(
            self.ui.pushButtonExportLogs, QtWidgets.QPushButton
        )
        self.assertIsInstance(
            self.ui.tableWidgetModules, QtWidgets.QTableWidget
        )
        self.assertIsInstance(self.ui.tabWidgetMain, QtWidgets.QTabWidget)
        self.assertIsInstance(self.ui.labelLogs, QtWidgets.QLabel)
        self.assertIsInstance(
            self.ui.labelProcessFinished, QtWidgets.QLabel
        )

        # The modules table is the data-bearing widget; lock in its
        # column count so a future regression to retranslateUi /
        # setupUi is loud.
        self.assertEqual(self.ui.tableWidgetModules.columnCount(), 4)

        # Two tabs: module states and logs, starting on the first one.
        self.assertEqual(self.ui.tabWidgetMain.count(), 2)
        self.assertEqual(self.ui.tabWidgetMain.currentIndex(), 0)

    def test_retranslate_applied(self) -> None:
        """User-visible strings from retranslateUi must be present.

        We only check a couple of representative strings (the window
        title and the WARNING label) rather than every translation,
        because the goal is to prove retranslateUi ran -- not to
        couple the test to copy edits.
        """
        self.ui.setupUi(self.dialog)  # type: ignore[no-untyped-call]

        self.assertEqual(
            self.dialog.windowTitle(), 'Missing modules warning'
        )
        # label_2 carries the big WARNING banner; the text is HTML.
        self.assertIn('WARNING', self.ui.label_2.text())
        # Buttons must have user-facing text after retranslateUi.
        self.assertTrue(self.ui.pushButtonInstall.text())
        self.assertTrue(self.ui.pushButtonLetUserInstall.text())


if __name__ == '__main__':
    suite = unittest.TestLoader().loadTestsFromModule(__import__(__name__))
    runner = unittest.TextTestRunner(verbosity=2)
    runner.run(suite)
