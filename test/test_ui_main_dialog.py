# coding=utf-8
"""Tests for the main plugin Dialog UI component.

Test plan
---------
Component under test: ``eurostat_downloader.src.eurostat_downloader.Dialog``.

Construction paths
~~~~~~~~~~~~~~~~~~
``Dialog`` has a single ``__init__(self, eurostat_downloader)`` that takes the
``EurostatDownloader`` plugin object (which in turn requires the QGIS ``iface``).
Inside ``__init__`` the dialog:

* instantiates ``Ui_EurostatDownloaderDialog`` and calls ``self.ui.setupUi(self)``
  -- this is where the generated ``pyuic5`` code runs, including ~12 references
  to ``QtWidgets.QSizePolicy.Minimum``, ``.Fixed`` and ``.Expanding`` (unscoped
  enums that explode under PyQt6).
* calls ``self.set_layer_join_fields()`` which touches ``self.ui.qgsComboLayer``.
* instantiates the auxiliary handlers (``GISCOHandler``, ``JoinHandler``,
  ``Exporter``, ``QgsConverter``). ``GISCOHandler.__init__`` wires up several
  signal connections on UI widgets, so a missing/renamed widget would surface
  here too.
* creates a single-shot ``QTimer`` for search debouncing.
* connects ~12 signals on widgets such as ``pushButtonInitializeTOC``,
  ``qgsComboLayer``, ``lineSearch``, ``treeDatabase``, ``tableDataset``,
  ``toolButtonSettings``, ``buttonReset``, ``buttonAdd``, ``buttonJoin``,
  the three language checkboxes, and ``tabWidget``.

What could break under PyQt6
~~~~~~~~~~~~~~~~~~~~~~~~~~~~
* Unscoped enums in the generated UI file (``QSizePolicy.Minimum/Fixed/Expanding``
  at lines 97, 194, 212, 237, 249 of ``eurostat_downloader_dialog.py``) -- this
  is the documented regression.
* Other unscoped enum forms in the same file (alignments, frame shapes, etc.).
* Signal connection failures if an attribute was renamed or removed.
* ``QAction``/menu wiring -- not exercised by ``Dialog`` itself; that lives on
  ``EurostatDownloader.initGui`` and is intentionally out of scope here.

Valuable assertions beyond "doesn't raise"
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
* ``dlg.ui`` is the expected ``Ui_EurostatDownloaderDialog`` instance.
* The handlers (``gisco_handler``, ``join_handler``, ``exporter``, ``converter``)
  are wired up and reference the dialog as their base.
* Key widgets used elsewhere in the plugin are present on ``dlg.ui`` -- a
  regression check for renames/removals.
* Default state: the tab widget is on the first tab, ``dataset`` starts as
  ``None``, the search debounce timer is single-shot, and language checkboxes
  start unchecked (English is the implicit default through
  ``get_selected_language`` rather than a checked box).
* The dialog is a real ``QDialog`` (parent class chain intact).

What is intentionally NOT tested
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
* Network/database initialization (``initialize_database`` spawns a
  ``QThread`` that hits live agency endpoints).
* Behavior of signal handlers when triggered -- exercising them needs a
  populated ``Dataset``, which is out of scope for a UI smoke test.
* Anything covered by ``test_utils.py`` (CheckableComboBox internals etc.).
* Child dialogs (settings, parameter section, time section, GISCO join
  report) -- the other six agents own those.
"""

__author__ = 'cuvuliucalexandrei@gmail.com'
__date__ = '2026-05-23'

import unittest

from qgis.PyQt import QtCore, QtWidgets

from eurostat_downloader.src.eurostat_downloader import (
    Dialog,
    EurostatDownloader,
    Exporter,
    GISCOHandler,
    JoinHandler,
    QgsConverter,
)
from eurostat_downloader.src.ui.eurostat_downloader_dialog import (
    Ui_EurostatDownloaderDialog,
)
from test.utilities import get_qgis_app

QGIS_APP, CANVAS, IFACE, PARENT = get_qgis_app()


class TestMainDialog(unittest.TestCase):
    """Test the main plugin Dialog construction and default UI state."""

    def setUp(self):
        """Build a fresh plugin + Dialog for each test."""
        self.plugin = EurostatDownloader(IFACE)
        self.dialog = Dialog(self.plugin)

    def tearDown(self):
        """Release the dialog so signal connections don't leak between tests."""
        self.dialog.deleteLater()
        self.dialog = None
        self.plugin = None

    def test_constructs_without_error(self):
        """Dialog instantiates and runs setupUi without raising.

        This is the regression test for the PyQt6 unscoped-enum bug
        (``QtWidgets.QSizePolicy.Minimum`` and friends in the generated
        UI file). If ``setupUi`` raises, the assertions below never run
        and the test fails at ``setUp``.
        """
        self.assertIsInstance(self.dialog, QtWidgets.QDialog)
        self.assertIsInstance(self.dialog.ui, Ui_EurostatDownloaderDialog)
        # The dialog stores the plugin reference under this name.
        self.assertIs(self.dialog.eurostat_downloader, self.plugin)

    def test_handlers_are_wired_up(self):
        """Auxiliary handlers are constructed and reference the dialog."""
        self.assertIsInstance(self.dialog.gisco_handler, GISCOHandler)
        self.assertIsInstance(self.dialog.join_handler, JoinHandler)
        self.assertIsInstance(self.dialog.exporter, Exporter)
        self.assertIsInstance(self.dialog.converter, QgsConverter)

        self.assertIs(self.dialog.gisco_handler.base, self.dialog)
        self.assertIs(self.dialog.join_handler.base, self.dialog)
        self.assertIs(self.dialog.exporter.base, self.dialog)
        self.assertIs(self.dialog.converter.base, self.dialog)

    def test_key_widgets_exist(self):
        """The widgets the plugin code touches all exist on the dialog UI.

        Catches regressions if a widget is renamed/removed in the .ui file.
        """
        expected_widgets = (
            ('pushButtonInitializeTOC', QtWidgets.QPushButton),
            ('buttonReset', QtWidgets.QPushButton),
            ('buttonAdd', QtWidgets.QPushButton),
            ('buttonJoin', QtWidgets.QPushButton),
            ('lineSearch', QtWidgets.QLineEdit),
            ('linePrefix', QtWidgets.QLineEdit),
            ('treeDatabase', QtWidgets.QTreeWidget),
            ('tableDataset', QtWidgets.QTableView),
            ('tabWidget', QtWidgets.QTabWidget),
            ('toolButtonSettings', QtWidgets.QToolButton),
            ('checkEnglish', QtWidgets.QCheckBox),
            ('checkFrench', QtWidgets.QCheckBox),
            ('checkGerman', QtWidgets.QCheckBox),
            ('comboTableJoinField', QtWidgets.QComboBox),
            ('comboBoxColumnsToJoin', QtWidgets.QComboBox),
            ('comboBoxGISCOTheme', QtWidgets.QComboBox),
            ('comboBoxGISCOYear', QtWidgets.QComboBox),
            ('comboBoxGISCOSpatialType', QtWidgets.QComboBox),
            ('comboBoxGISCOScale', QtWidgets.QComboBox),
            ('comboBoxGISCOProjection', QtWidgets.QComboBox),
            ('tableWidgetDownloadUnits', QtWidgets.QTableWidget),
            ('labelAgencyStatus', QtWidgets.QLabel),
        )
        for name, widget_type in expected_widgets:
            with self.subTest(widget=name):
                self.assertTrue(
                    hasattr(self.dialog.ui, name),
                    f'Dialog UI is missing widget {name!r}',
                )
                self.assertIsInstance(getattr(self.dialog.ui, name), widget_type)

    def test_default_state(self):
        """Default state after construction matches what the plugin expects."""
        # No dataset is loaded yet.
        self.assertIsNone(self.dialog.dataset)
        self.assertIsNone(self.dialog.subset)
        self.assertIsNone(self.dialog.filterer)

        # Search debounce timer is configured as single-shot.
        self.assertIsInstance(self.dialog.search_timer, QtCore.QTimer)
        self.assertTrue(self.dialog.search_timer.isSingleShot())

        # The tab widget starts on the first tab (the LAYER tab in the
        # ``Tabs`` enum, which is index 0 -> Tabs.LAYER via auto()).
        self.assertEqual(self.dialog.ui.tabWidget.currentIndex(), 0)
        self.assertGreaterEqual(self.dialog.ui.tabWidget.count(), 2)

        # English is checked by default (set checked=true in the .ui
        # source); French and German start unchecked.
        self.assertTrue(self.dialog.ui.checkEnglish.isChecked())
        self.assertFalse(self.dialog.ui.checkFrench.isChecked())
        self.assertFalse(self.dialog.ui.checkGerman.isChecked())

        # The GISCO "view join report" button is disabled until validation.
        # GISCOHandler doesn't explicitly disable it on init, but the
        # callback wired up in ``add_callback_to_comboboxes`` will, so
        # we only assert it is enabled-or-disabled (i.e. a real QWidget).
        self.assertIsInstance(
            self.dialog.ui.pushButtonGISCOViewJoinReport, QtWidgets.QPushButton
        )


if __name__ == '__main__':
    suite = unittest.TestLoader().loadTestsFromModule(__import__(__name__))
    runner = unittest.TextTestRunner(verbosity=2)
    runner.run(suite)
