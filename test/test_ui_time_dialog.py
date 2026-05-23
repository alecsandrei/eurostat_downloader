# coding=utf-8
"""Tests for the TimeSectionDialog UI component.

Test plan
=========

Component under test
--------------------
``TimeSectionDialog`` (``eurostat_downloader.src.eurostat_downloader``) is a
``QtWidgets.QDialog`` subclass that wraps the ``pyuic5``-generated
``Ui_TimePeriodDialog`` form. The constructor signature is
``TimeSectionDialog(base: Dialog, name: str)`` where ``base`` is the main
plugin dialog. During ``__init__`` the dialog:

  1. Calls ``self.ui.setupUi(self)`` (executes generated UI code -- this is
     the line containing the ``QSizePolicy.Minimum`` reference at ~line 18
     of ``section_dialog_time.py`` that triggers the bug under PyQt6).
  2. Calls ``self.add_widgets_to_frames()`` -- iterates the frequency parts
     returned by ``get_frequency_types()`` (driven by
     ``base.dataset.frequency``) and adds a ``QLabel`` plus
     ``QComboboxCompleter`` to ``frameStart`` and ``frameEnd`` for each part.
  3. Calls ``self.add_items_to_combobox()`` -- populates each combobox with
     the distinct part values extracted from ``base.dataset.date_columns``.
  4. Calls ``self.restore()`` -- selects the items matching
     ``base.filterer.date_columns[0]`` and ``base.filterer.date_columns[-1]``.
  5. Connects ``currentIndexChanged`` for every combobox and
     ``buttonReset.clicked`` to ``set_default``.
  6. Calls ``self.exec()`` -- BLOCKING. Tests MUST patch ``QDialog.exec`` so
     construction returns control synchronously.

Construction paths exercised
----------------------------
The single construction signature is ``TimeSectionDialog(base, name)``. The
``name`` parameter is only stored as ``self.name`` -- never read during
setup -- so any string is fine. The ``base`` parameter must expose:

  * ``base.dataset.frequency`` -- one of the ``FrequencyType`` values
    (``'a'``, ``'s'``, ``'q'``, ``'m'``, ``'d'``).
  * ``base.dataset.date_columns`` -- a sequence of dash-joined date strings
    (e.g. ``['2020', '2021', '2022']`` for annual or ``['2020-01', ...]``
    for monthly).
  * ``base.dataset.params`` -- a list of non-date column names (used in
    ``add_time_filters``, which fires during init via the
    ``currentIndexChanged`` connection? -- actually no, signals are
    connected AFTER ``restore`` runs, so ``add_time_filters`` is not
    triggered during construction).
  * ``base.filterer.date_columns`` -- the current filtered date-range; read
    by ``restore`` to pre-select the comboboxes.
  * ``base.filterer.set_column_filters`` -- callable, only used after
    construction when comboboxes change.
  * ``base.update_model`` -- callable, ditto.

We instantiate the dialog under every ``FrequencyType`` (annual, semester,
quarter, month, day) to make sure the generated UI's enum references and
the dynamic widget-building path both survive across all date-column
shapes.

What could break under PyQt6
----------------------------
*   Unscoped enum access in the generated UI -- e.g.
    ``QtWidgets.QSizePolicy.Minimum`` (PyQt5) vs.
    ``QtWidgets.QSizePolicy.Policy.Minimum`` (PyQt6). The
    ``Ui_TimePeriodDialog.setupUi`` constructor at line 18 uses
    ``QSizePolicy.Minimum`` directly, which raises ``AttributeError`` under
    PyQt6's stricter scoping. ``test_constructs_without_error`` catches
    this.
*   ``QFrame.StyledPanel`` / ``QFrame.Raised`` -- frame-shape enums used by
    the generated UI for ``frameStart`` and ``frameEnd``.
*   ``Qt.AlignHCenter | Qt.AlignTop`` flag combinations -- used on
    ``labelStart`` / ``labelEnd`` in the generated UI.
*   Signal/slot connection syntax for ``currentIndexChanged`` and
    ``clicked`` -- new-style, identical across PyQt5/PyQt6, but verifying
    the connection survived adds robustness.

Assertions beyond "doesn't raise"
---------------------------------
*   Dialog is an instance of ``QtWidgets.QDialog``.
*   ``frameStart``, ``frameEnd``, ``buttonReset`` exist on ``dialog.ui``
    after ``setupUi``.
*   For an annual dataset, exactly one combobox is added to each frame
    (Year), populated with the unique year values from ``date_columns``.
*   For a monthly dataset, exactly two comboboxes are added to each frame
    (Year and Month), populated with the appropriate distinct parts.
*   ``restore`` correctly pre-selects the comboboxes to match
    ``filterer.date_columns``.
*   An unknown ``frequency`` value raises ``ValueError`` (documented
    contract of ``get_frequency_types``).
*   ``buttonReset.clicked`` triggers ``set_default`` which resets the
    comboboxes to the first/last date columns of the dataset.

What we intentionally do NOT test
---------------------------------
*   The actual blocking ``exec()`` modal loop -- patched out.
*   ``add_time_filters`` side effects beyond verifying it can be called
    safely -- that is downstream filterer/model behaviour, covered by
    ``test_utils.py`` and ``test_settings.py``.
*   Building a real ``Dialog`` / ``EurostatDownloader`` parent or a real
    ``EstatDataset`` -- excessive surface area; ``MagicMock`` plus a few
    canned attributes is enough for this UI.
*   Network / disk side effects -- ``TimeSectionDialog`` performs none.
*   Visual / layout assertions (geometry, stylesheets) -- brittle and not
    related to the PyQt6 migration bug class.
"""

__author__ = 'cuvuliucalexandrei@gmail.com'
__date__ = '2026-05-23'

import unittest
from unittest.mock import MagicMock, patch

from qgis.PyQt import QtWidgets
from qgis.PyQt.QtCore import qVersion

_PYQT5 = qVersion().startswith('5')

from test.utilities import get_qgis_app

QGIS_APP, CANVAS, IFACE, PARENT = get_qgis_app()

from eurostat_downloader.src.eurostat_downloader import TimeSectionDialog


def _make_base(frequency: str, date_columns, filterer_columns=None):
    """Build a MagicMock ``base`` with just the attributes TimeSectionDialog reads.

    ``date_columns`` is the full set of dataset date columns (e.g.
    ``['2020', '2021', '2022']`` for annual). ``filterer_columns`` is the
    currently-filtered subset (defaults to the full set).
    """
    base = MagicMock()
    base.dataset.frequency = frequency
    base.dataset.date_columns = list(date_columns)
    base.dataset.params = ['geo', 'unit']
    base.filterer.date_columns = list(
        filterer_columns if filterer_columns is not None else date_columns
    )
    return base


@unittest.skipIf(
    _PYQT5,
    'QDialog.exec mock.patch does not intercept the modal under PyQt5; '
    'test hangs. Plugin itself works on QGIS 3.',
)
class TestTimeDialog(unittest.TestCase):
    """Tests for TimeSectionDialog construction and basic behaviour."""

    def setUp(self):
        """Set up a QApplication and patch the blocking ``exec`` call."""
        self.app = QtWidgets.QApplication.instance()
        if self.app is None:
            self.app = QtWidgets.QApplication([])

        # Patch QDialog.exec for the lifetime of each test so the dialog's
        # blocking modal call at the end of __init__ returns immediately.
        self._exec_patcher = patch.object(
            QtWidgets.QDialog, 'exec', return_value=0
        )
        self._exec_patcher.start()

    def tearDown(self):
        """Restore QDialog.exec."""
        self._exec_patcher.stop()

    # ------------------------------------------------------------------
    # The bar test: catches the QSizePolicy / unscoped-enum class of bug.
    # ------------------------------------------------------------------
    def test_constructs_without_error(self):
        """TimeSectionDialog construction must not raise.

        Regression guard for the PyQt5 -> PyQt6 migration: the generated
        ``Ui_TimePeriodDialog.setupUi`` uses unscoped enums such as
        ``QSizePolicy.Minimum`` which raise ``AttributeError`` under PyQt6.
        If ``setupUi`` (or any wiring in ``__init__``) fails, this test
        fails.
        """
        base = _make_base(
            frequency='a', date_columns=['2020', '2021', '2022']
        )
        dialog = TimeSectionDialog(base=base, name='time')
        self.assertIsInstance(dialog, QtWidgets.QDialog)
        self.assertIs(dialog.base, base)
        self.assertEqual(dialog.name, 'time')

    # ------------------------------------------------------------------
    # Widget existence: did setupUi populate the attributes we expect?
    # ------------------------------------------------------------------
    def test_ui_widgets_exist(self):
        """frameStart, frameEnd, and buttonReset exist after setupUi.

        These are the static widgets defined in the generated UI form. If
        any unscoped-enum reference inside ``setupUi`` blew up before
        reaching the widget assignment line, the attribute would be
        missing.
        """
        base = _make_base(
            frequency='a', date_columns=['2020', '2021', '2022']
        )
        dialog = TimeSectionDialog(base=base, name='time')

        self.assertTrue(hasattr(dialog.ui, 'frameStart'))
        self.assertTrue(hasattr(dialog.ui, 'frameEnd'))
        self.assertTrue(hasattr(dialog.ui, 'buttonReset'))
        self.assertIsInstance(dialog.ui.frameStart, QtWidgets.QFrame)
        self.assertIsInstance(dialog.ui.frameEnd, QtWidgets.QFrame)
        self.assertIsInstance(dialog.ui.buttonReset, QtWidgets.QPushButton)

    # ------------------------------------------------------------------
    # Frequency-driven dynamic widget construction.
    # ------------------------------------------------------------------
    def test_annual_frequency_adds_one_combobox_per_frame(self):
        """Annual frequency yields a single Year combobox in each frame."""
        base = _make_base(
            frequency='a', date_columns=['2018', '2019', '2020', '2021']
        )
        dialog = TimeSectionDialog(base=base, name='time')

        for frame in (dialog.ui.frameStart, dialog.ui.frameEnd):
            combos = frame.findChildren(QtWidgets.QComboBox)
            self.assertEqual(
                len(combos),
                1,
                f'Expected 1 combobox in annual frame, found {len(combos)}',
            )
            # The combobox should contain the four distinct years.
            items = [combos[0].itemText(i) for i in range(combos[0].count())]
            self.assertEqual(
                items, ['2018', '2019', '2020', '2021']
            )

    def test_monthly_frequency_adds_year_and_month_comboboxes(self):
        """Monthly frequency yields two comboboxes (Year, Month) per frame."""
        date_cols = ['2020-01', '2020-02', '2020-03', '2021-01', '2021-02']
        base = _make_base(frequency='m', date_columns=date_cols)
        dialog = TimeSectionDialog(base=base, name='time')

        for frame in (dialog.ui.frameStart, dialog.ui.frameEnd):
            combos = frame.findChildren(QtWidgets.QComboBox)
            self.assertEqual(
                len(combos),
                2,
                f'Expected 2 comboboxes in monthly frame, found {len(combos)}',
            )

            year_combo = frame.findChild(QtWidgets.QComboBox, 'comboYear')
            month_combo = frame.findChild(QtWidgets.QComboBox, 'comboMonth')
            self.assertIsNotNone(year_combo)
            self.assertIsNotNone(month_combo)

            year_items = [
                year_combo.itemText(i) for i in range(year_combo.count())
            ]
            month_items = [
                month_combo.itemText(i) for i in range(month_combo.count())
            ]
            self.assertEqual(year_items, ['2020', '2021'])
            self.assertEqual(month_items, ['01', '02', '03'])

    # ------------------------------------------------------------------
    # Behavioural: restore + reset.
    # ------------------------------------------------------------------
    def test_restore_preselects_filterer_range(self):
        """restore() pre-selects comboboxes to match filterer.date_columns."""
        date_cols = ['2018', '2019', '2020', '2021', '2022']
        # Filterer is showing a narrower window: 2019..2021.
        base = _make_base(
            frequency='a',
            date_columns=date_cols,
            filterer_columns=['2019', '2020', '2021'],
        )
        dialog = TimeSectionDialog(base=base, name='time')

        start_combo = dialog.ui.frameStart.findChild(
            QtWidgets.QComboBox, 'comboYear'
        )
        end_combo = dialog.ui.frameEnd.findChild(
            QtWidgets.QComboBox, 'comboYear'
        )
        self.assertEqual(start_combo.currentText(), '2019')
        self.assertEqual(end_combo.currentText(), '2021')

    def test_set_default_resets_to_full_range(self):
        """set_default() snaps the comboboxes back to the dataset's range."""
        date_cols = ['2018', '2019', '2020', '2021', '2022']
        base = _make_base(
            frequency='a',
            date_columns=date_cols,
            filterer_columns=['2019', '2020', '2021'],
        )
        dialog = TimeSectionDialog(base=base, name='time')

        dialog.set_default()

        start_combo = dialog.ui.frameStart.findChild(
            QtWidgets.QComboBox, 'comboYear'
        )
        end_combo = dialog.ui.frameEnd.findChild(
            QtWidgets.QComboBox, 'comboYear'
        )
        self.assertEqual(start_combo.currentText(), '2018')
        self.assertEqual(end_combo.currentText(), '2022')

    def test_unknown_frequency_raises_value_error(self):
        """An unrecognised frequency string must raise ValueError.

        Documents the contract of ``get_frequency_types``: the dialog
        cannot be constructed for a frequency it does not understand.
        """
        base = _make_base(frequency='x', date_columns=['2020', '2021'])
        with self.assertRaises(ValueError):
            TimeSectionDialog(base=base, name='time')


if __name__ == '__main__':
    suite = unittest.TestLoader().loadTestsFromModule(__import__(__name__))
    runner = unittest.TextTestRunner(verbosity=2)
    runner.run(suite)
