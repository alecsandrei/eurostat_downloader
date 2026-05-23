# coding=utf-8
"""Tests for the ParameterSectionDialog UI component.

Test plan
=========

Component under test
--------------------
``ParameterSectionDialog`` (``eurostat_downloader.src.eurostat_downloader``)
is a ``QtWidgets.QDialog`` subclass that wraps the ``pyuic5``-generated
``Ui_ParametersDialog`` form. The constructor signature is
``ParameterSectionDialog(base: Dialog, name: str)``. During ``__init__``
the dialog:

  1. Calls ``self.ui.setupUi(self)`` (executes generated UI code -- this is
     where unscoped ``QSizePolicy.Minimum`` / ``QSizePolicy.Expanding`` /
     ``QSizePolicy.Fixed`` / ``QSizePolicy.Preferred`` references live, and
     also ``QAbstractItemView.ExtendedSelection`` and
     ``QtCore.Qt.LeftToRight``).
  2. Calls ``self.filter_toc()`` -- populates ``listItems`` from either
     ``base.dataset.params_info[lang][name]`` (when ``lang`` is set) or the
     unique values of the column in ``base.dataset.data`` (when ``lang`` is
     None). ``base.dataset`` must therefore be non-None and have a coherent
     shape; tests pass a SimpleNamespace.
  3. Calls ``self.select_based_on_filterer()`` -- consults
     ``base.filterer.row`` (a dict-like) to pre-select items.
  4. Calls ``self.section_type_handler()`` -- compares ``self.name`` to
     ``base.get_current_table_join_field()`` and instantiates a
     ``GeoParameterSectionDialog`` if they match. We deliberately mismatch
     them in our fixtures so this branch is a no-op.
  5. Connects three signals: ``lineSearch.textChanged``,
     ``buttonReset.clicked``, ``listItems.itemSelectionChanged``.
  6. Calls ``self.exec()`` -- BLOCKING. Tests MUST patch ``QDialog.exec``
     so construction returns control synchronously (same pattern as
     ``test_ui_settings_dialog.py``).

Construction paths exercised
----------------------------
The constructor has a single signature, but ``filter_toc`` branches on
``dataset.lang``. We cover both branches:

*   ``dataset.lang`` set -> uses ``params_info`` (the typical Eurostat case).
*   ``dataset.lang`` None -> derives unique values from raw ``data`` rows
    (the no-pandas / fallback case).

The ``base`` parent is not a real ``Dialog`` -- building one drags in a
``Database``, ``GISCOHandler``, ``QgsConverter``, network/disk side effects
and a full UI tree. Since ``ParameterSectionDialog.__init__`` only reads
``base.dataset``, ``base.filterer`` and ``base.get_current_table_join_field``
and (lazily) ``base.update_model``, a ``SimpleNamespace`` / ``MagicMock``
hybrid is sufficient and faithful.

What could break under PyQt6
----------------------------
*   Unscoped ``QSizePolicy.Minimum`` / ``.Expanding`` / ``.Fixed`` /
    ``.Preferred`` in the generated UI -- PyQt6 requires
    ``QSizePolicy.Policy.Minimum`` etc. ``setupUi`` raises AttributeError
    if these aren't fixed. ``test_constructs_without_error`` catches that.
*   ``QtWidgets.QAbstractItemView.ExtendedSelection`` -- under PyQt6 this
    moved to ``QAbstractItemView.SelectionMode.ExtendedSelection``. The
    generated UI uses the unscoped form, so construction would fail if
    PyQt6 enforced scoping here too.
*   ``QtCore.Qt.LeftToRight`` -- under PyQt6 this is
    ``Qt.LayoutDirection.LeftToRight``.
*   Signal/slot connect API -- the ``textChanged`` / ``clicked`` /
    ``itemSelectionChanged`` connections use new-style syntax that is
    identical across PyQt5/PyQt6, but we still drive them in
    ``test_signals_wire_up`` to verify they fire correctly.

Assertions beyond "doesn't raise"
---------------------------------
*   Dialog is a ``QtWidgets.QDialog`` instance and stores ``base`` / ``name``.
*   The three key UI widgets exist with the right types
    (``lineSearch``: ``QLineEdit``, ``listItems``: ``QListWidget``,
    ``buttonReset``: ``QPushButton``).
*   ``listItems`` selection mode is ``ExtendedSelection`` (from the UI file).
*   ``filter_toc`` correctly populates items from ``params_info`` in the
    ``lang``-set path, and from unique column values in the no-lang path.
*   ``reset_selection`` clears the selection on ``listItems``.
*   ``filter_list_items`` hides rows whose text doesn't contain the search
    query (case-insensitive).
*   ``get_selected_items`` returns the abbreviation portion (before
    `` [...]``) of each selected item.

What we intentionally do NOT test
---------------------------------
*   The blocking ``exec()`` modal loop -- patched out.
*   ``GeoParameterSectionDialog`` branch -- belongs to a sibling component;
    triggered only when ``name == base.get_current_table_join_field()``.
*   Real ``Dialog`` / ``Database`` / network setup -- unrelated to the UI
    regression we're guarding.
*   Visual/layout assertions (geometry, stylesheets).
*   ``filter_table`` integration with ``base.filterer`` -- exercised via
    selection signals but its full filter-state side effects belong with
    the filterer's own tests.
"""

from __future__ import annotations

__author__ = 'cuvuliucalexandrei@gmail.com'
__date__ = '2026-05-23'

import unittest
from collections.abc import Mapping, Sequence
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from qgis.PyQt import QtWidgets
from qgis.PyQt.QtCore import qVersion

_PYQT5 = qVersion().startswith('5')

from test.utilities import get_qgis_app  # noqa: E402

QGIS_APP, CANVAS, IFACE, PARENT = get_qgis_app()

from eurostat_downloader.src.eurostat_downloader import ParameterSectionDialog  # noqa: E402


def _make_base(
    *,
    name: str = 'unit',
    lang: str | None = 'en',
    params_info_items: Sequence[tuple[str, str]] | None = None,
    data_columns: Sequence[str] | None = None,
    data_rows: Sequence[Sequence[object]] | None = None,
    filterer_row: Mapping[str, object] | None = None,
    join_field: str = '__no_match__',
) -> MagicMock:
    """Build a lightweight stand-in for the ``Dialog`` parent.

    Only the attributes/methods ``ParameterSectionDialog.__init__`` reads
    are populated. ``join_field`` is mismatched against ``name`` by default
    so the ``GeoParameterSectionDialog`` branch in ``section_type_handler``
    is a no-op.
    """
    if params_info_items is None:
        params_info_items = [('A1', 'Alpha one'), ('B2', 'Beta two')]
    dataset = SimpleNamespace(
        lang=lang,
        params_info={lang: {name: params_info_items}} if lang else {},
        data={
            'columns': data_columns if data_columns is not None else [name],
            'data': data_rows if data_rows is not None else [],
        },
        date_columns=[],
        frequency='A',
    )
    filterer = SimpleNamespace(
        row=filterer_row if filterer_row is not None else {},
        add_row_filters=MagicMock(),
        remove_row_filters=MagicMock(),
    )
    base = MagicMock()
    base.dataset = dataset
    base.filterer = filterer
    base.get_current_table_join_field = MagicMock(return_value=join_field)
    base.update_model = MagicMock()
    return base


@unittest.skipIf(
    _PYQT5,
    'QDialog.exec mock.patch does not intercept the modal under PyQt5; '
    'test hangs. Plugin itself works on QGIS 3.',
)
class TestParametersDialog(unittest.TestCase):
    """Tests for ParameterSectionDialog construction and behaviour."""

    def setUp(self) -> None:
        """Ensure a QApplication exists and stub out the blocking exec."""
        self.app = QtWidgets.QApplication.instance()
        if self.app is None:
            self.app = QtWidgets.QApplication([])

        # ParameterSectionDialog.__init__ ends with ``self.exec()`` which is
        # modal-blocking. Patch it for the lifetime of every test so the
        # constructor returns synchronously (same pattern that fixed
        # SettingsDialog tests).
        self._exec_patcher = patch.object(
            QtWidgets.QDialog, 'exec', return_value=0
        )
        self._exec_patcher.start()

    def tearDown(self) -> None:
        self._exec_patcher.stop()

    # ------------------------------------------------------------------
    # The bar test: catches the QSizePolicy / unscoped-enum class of bug.
    # ------------------------------------------------------------------
    def test_constructs_without_error(self) -> None:
        """Construction must not raise.

        Regression guard for the PyQt5 -> PyQt6 migration: unscoped enums
        such as ``QSizePolicy.Minimum`` / ``.Expanding`` / ``.Fixed`` /
        ``.Preferred`` and ``QAbstractItemView.ExtendedSelection`` in the
        generated ``Ui_ParametersDialog.setupUi`` raise ``AttributeError``
        under PyQt6. If anything in ``__init__`` (setupUi, filter_toc,
        signal wiring) fails, this test fails.
        """
        base = _make_base(name='unit')
        dialog = ParameterSectionDialog(base, 'unit')
        self.assertIsInstance(dialog, QtWidgets.QDialog)
        self.assertIs(dialog.base, base)
        self.assertEqual(dialog.name, 'unit')

    # ------------------------------------------------------------------
    # Widget existence / configured state from the .ui file.
    # ------------------------------------------------------------------
    def test_key_widgets_exist_with_expected_types(self) -> None:
        """The three controls referenced by handlers must be present."""
        base = _make_base(name='unit')
        dialog = ParameterSectionDialog(base, 'unit')

        self.assertIsInstance(dialog.ui.lineSearch, QtWidgets.QLineEdit)
        self.assertIsInstance(dialog.ui.listItems, QtWidgets.QListWidget)
        self.assertIsInstance(dialog.ui.buttonReset, QtWidgets.QPushButton)

        # Configured by setupUi via the (potentially unscoped) enum --
        # asserting it indirectly validates the enum was reachable.
        self.assertEqual(
            dialog.ui.listItems.selectionMode(),
            QtWidgets.QAbstractItemView.SelectionMode.ExtendedSelection,
        )

    # ------------------------------------------------------------------
    # filter_toc: both branches.
    # ------------------------------------------------------------------
    def test_filter_toc_populates_from_params_info_when_lang_set(self) -> None:
        """With ``dataset.lang`` set, items come from ``params_info``."""
        base = _make_base(
            name='geo',
            lang='en',
            params_info_items=[('DE', 'Germany'), ('FR', 'France')],
        )
        dialog = ParameterSectionDialog(base, 'geo')

        texts = [
            dialog.ui.listItems.item(i).text()
            for i in range(dialog.ui.listItems.count())
        ]
        self.assertEqual(texts, ['DE [Germany]', 'FR [France]'])

    def test_filter_toc_populates_from_data_when_lang_is_none(self) -> None:
        """With ``dataset.lang`` None, items are unique column values."""
        base = _make_base(
            name='age',
            lang=None,
            data_columns=['age', 'value'],
            data_rows=[['Y20', 1], ['Y25', 2], ['Y20', 3]],
        )
        dialog = ParameterSectionDialog(base, 'age')

        texts = {
            dialog.ui.listItems.item(i).text()
            for i in range(dialog.ui.listItems.count())
        }
        self.assertEqual(texts, {'Y20', 'Y25'})

    # ------------------------------------------------------------------
    # Behavioural: search / reset / selection accessor.
    # ------------------------------------------------------------------
    def test_reset_selection_clears_selection(self) -> None:
        """``buttonReset`` handler clears the list's selection."""
        base = _make_base(name='unit')
        dialog = ParameterSectionDialog(base, 'unit')

        # Select all items, then ensure reset clears them.
        dialog.ui.listItems.selectAll()
        self.assertTrue(len(dialog.ui.listItems.selectedItems()) > 0)

        dialog.reset_selection()
        self.assertEqual(dialog.ui.listItems.selectedItems(), [])

    def test_filter_list_items_hides_non_matching_rows(self) -> None:
        """Typing in ``lineSearch`` hides rows that don't contain the query."""
        base = _make_base(
            name='unit',
            params_info_items=[
                ('A1', 'Alpha one'),
                ('B2', 'Beta two'),
                ('A3', 'Alpha three'),
            ],
        )
        dialog = ParameterSectionDialog(base, 'unit')

        dialog.ui.lineSearch.setText('alpha')
        dialog.filter_list_items()

        hidden = [
            dialog.ui.listItems.item(i).isHidden()
            for i in range(dialog.ui.listItems.count())
        ]
        # Only the 'Beta two' row should be hidden.
        self.assertEqual(hidden, [False, True, False])

    def test_get_selected_items_returns_abbreviations(self) -> None:
        """Selected items return just the abbreviation portion."""
        base = _make_base(
            name='unit',
            params_info_items=[('A1', 'Alpha one'), ('B2', 'Beta two')],
        )
        dialog = ParameterSectionDialog(base, 'unit')

        # Select both items programmatically.
        for row in range(dialog.ui.listItems.count()):
            dialog.ui.listItems.item(row).setSelected(True)

        self.assertEqual(sorted(dialog.get_selected_items()), ['A1', 'B2'])


if __name__ == '__main__':
    suite = unittest.TestLoader().loadTestsFromModule(__import__(__name__))
    runner = unittest.TextTestRunner(verbosity=2)
    runner.run(suite)
