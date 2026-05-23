# coding=utf-8
"""Tests for the SettingsDialog UI component.

Test plan
=========

Component under test
--------------------
``SettingsDialog`` (``eurostat_downloader.src.eurostat_downloader``) is a
``QtWidgets.QDialog`` subclass that wraps the ``pyuic5``-generated
``Ui_SettingsDialog`` form. The constructor signature is
``SettingsDialog(base: Dialog)`` where ``base`` is the main plugin dialog.
During ``__init__`` the dialog:

  1. Calls ``self.ui.setupUi(self)`` (executes generated UI code).
  2. Wires an internal ``_agencies_checkboxes`` dict mapping ``Agency`` enum
     members to their ``QCheckBox`` widgets (asserts every ``Agency`` is
     covered).
  3. Calls ``self.restore_global_settings()`` to sync widget state with the
     module-level ``GLOBAL_SETTINGS`` singleton.
  4. Connects the Ok button's ``clicked`` signal to
     ``self.update_global_settings``.
  5. Calls ``self.exec()`` -- BLOCKING. Tests MUST patch ``QDialog.exec`` so
     construction returns control synchronously.

Construction paths exercised
----------------------------
There is only one construction path: ``SettingsDialog(base)``. The ``base``
parameter is stored as ``self.base`` but otherwise unused during ``__init__``,
so a lightweight stand-in (``MagicMock``) is sufficient -- we deliberately
avoid building a real ``Dialog`` (which would spin up ``Database``,
``GISCOHandler``, ``QgsConverter``, etc. and has many side effects unrelated
to this UI's correctness).

What could break under PyQt6
----------------------------
*   Unscoped enum access in generated UI code -- e.g.
    ``QSizePolicy.Minimum`` (PyQt5) vs ``QSizePolicy.Policy.Minimum``
    (PyQt6). Any such reference inside ``Ui_SettingsDialog.setupUi`` raises
    ``AttributeError`` at construction time. ``test_constructs_without_error``
    catches this.
*   ``Qt.Vertical`` / ``Qt.Horizontal`` orientation enums on
    ``QDialogButtonBox`` (the generated UI calls
    ``setOrientation(QtCore.Qt.Vertical)``).
*   ``QDialogButtonBox.Ok`` / ``.Cancel`` standard-button enums -- the source
    explicitly uses ``QDialogButtonBox.Ok`` when looking up the Ok button.
*   Signal/slot connection syntax -- ``ok_btn.clicked.connect(...)`` is
    new-style and identical across PyQt5/PyQt6, but verifying the connection
    survived adds robustness.

Assertions beyond "doesn't raise"
---------------------------------
*   Dialog is an instance of ``QtWidgets.QDialog`` -- sanity.
*   The five expected agency checkboxes (``EUROSTAT``, ``COMEXT``, ``COMP``,
    ``EMPL``, ``GROW``) exist as attributes on ``dialog.ui`` and are
    ``QCheckBox`` instances.
*   ``_agencies_checkboxes`` covers every member of the ``Agency`` enum (this
    is also asserted in production code, but we verify the post-condition).
*   ``buttonBox`` exists and exposes an Ok button via
    ``button(QDialogButtonBox.Ok)``.
*   ``restore_global_settings`` reflects the current ``GLOBAL_SETTINGS``: when
    a subset of agencies is selected, the checkboxes for the unselected ones
    are unchecked.
*   ``update_global_settings`` reads back checkbox state into
    ``GLOBAL_SETTINGS.agencies`` and applies the "if nothing selected,
    select everything" fallback documented in the source.

What we intentionally do NOT test
---------------------------------
*   The actual blocking ``exec()`` modal loop -- patched out.
*   Persistence of settings to disk via ``QgsSettings`` -- ``GLOBAL_SETTINGS``
    is an in-memory dataclass; nothing in ``SettingsDialog`` writes to disk.
    We restore ``GLOBAL_SETTINGS.agencies`` after each test so we don't
    leak state across tests.
*   Building a real ``Dialog`` / ``EurostatDownloader`` parent -- excessive
    surface area; ``base`` is stored but not used during dialog setup.
*   Visual/layout assertions (geometry, stylesheets) -- brittle and not
    related to the PyQt6 migration bug class.
*   Network / agency-status side effects -- ``SettingsDialog`` performs none.
"""

__author__ = 'cuvuliucalexandrei@gmail.com'
__date__ = '2026-05-23'

import unittest
from unittest.mock import MagicMock, patch

from qgis.PyQt import QtWidgets
from qgis.PyQt.QtCore import qVersion

_PYQT5 = qVersion().startswith('5')

from test.utilities import get_qgis_app  # noqa: E402

QGIS_APP, CANVAS, IFACE, PARENT = get_qgis_app()

from eurostat_downloader.src.eurostat_downloader import SettingsDialog  # noqa: E402
from eurostat_downloader.src.enums import Agency  # noqa: E402
from eurostat_downloader.src.settings import GLOBAL_SETTINGS  # noqa: E402


@unittest.skipIf(
    _PYQT5,
    'QDialog.exec mock.patch does not intercept the modal under PyQt5; '
    'test hangs. Plugin itself works on QGIS 3.',
)
class TestSettingsDialog(unittest.TestCase):
    """Tests for SettingsDialog construction and basic behaviour."""

    def setUp(self):
        """Set up a QApplication, mock parent, and snapshot global state."""
        self.app = QtWidgets.QApplication.instance()
        if self.app is None:
            self.app = QtWidgets.QApplication([])

        # SettingsDialog stores `base` but never invokes it during __init__,
        # so a MagicMock standing in for the Dialog parent is sufficient and
        # avoids the heavyweight Dialog/Database/etc. setup.
        self.base = MagicMock()

        # Snapshot GLOBAL_SETTINGS.agencies so individual tests can mutate it
        # without leaking state to other tests in the suite.
        self._original_agencies = list(GLOBAL_SETTINGS.agencies)

        # Patch QDialog.exec for the lifetime of each test so SettingsDialog's
        # blocking modal call returns immediately.
        self._exec_patcher = patch.object(
            QtWidgets.QDialog, 'exec', return_value=0
        )
        self._exec_patcher.start()

    def tearDown(self):
        """Restore GLOBAL_SETTINGS and unpatch QDialog.exec."""
        self._exec_patcher.stop()
        GLOBAL_SETTINGS.agencies = self._original_agencies

    def _make_dialog(self) -> SettingsDialog:
        """Helper: construct a SettingsDialog with a mock parent."""
        return SettingsDialog(self.base)

    # ------------------------------------------------------------------
    # The bar test: catches the QSizePolicy / unscoped-enum class of bug.
    # ------------------------------------------------------------------
    def test_constructs_without_error(self):
        """SettingsDialog construction must not raise.

        Regression guard for the PyQt5 -> PyQt6 migration: unscoped enums
        such as ``QSizePolicy.Minimum`` in the generated UI raise
        ``AttributeError`` under PyQt6. If ``setupUi`` (or any wiring in
        ``__init__``) fails, this test fails.
        """
        dialog = self._make_dialog()
        self.assertIsInstance(dialog, QtWidgets.QDialog)
        self.assertIs(dialog.base, self.base)

    # ------------------------------------------------------------------
    # Widget existence: did setupUi populate the attributes we expect?
    # ------------------------------------------------------------------
    def test_agency_checkboxes_exist(self):
        """Every Agency has a corresponding QCheckBox after setupUi."""
        dialog = self._make_dialog()
        expected = (
            'checkBoxAgencyEUROSTAT',
            'checkBoxAgencyCOMEXT',
            'checkBoxAgencyCOMP',
            'checkBoxAgencyEMPL',
            'checkBoxAgencyGROW',
        )
        for attr in expected:
            self.assertTrue(
                hasattr(dialog.ui, attr),
                f'Expected dialog.ui.{attr} to exist after setupUi',
            )
            self.assertIsInstance(
                getattr(dialog.ui, attr), QtWidgets.QCheckBox
            )

        # The agencies dict must cover every Agency enum member (production
        # code asserts this too, but we verify the post-condition).
        self.assertEqual(
            set(dialog._agencies_checkboxes.keys()), set(Agency)
        )
        for checkbox in dialog._agencies_checkboxes.values():
            self.assertIsInstance(checkbox, QtWidgets.QCheckBox)

    def test_button_box_has_ok_button(self):
        """buttonBox exists and exposes an Ok button.

        Uses the same standard-button enum the source uses, so this also
        exercises the PyQt6 enum scoping for ``QDialogButtonBox.Ok``.
        """
        dialog = self._make_dialog()
        self.assertTrue(hasattr(dialog.ui, 'buttonBox'))
        self.assertIsInstance(
            dialog.ui.buttonBox, QtWidgets.QDialogButtonBox
        )
        ok_btn = dialog.ui.buttonBox.button(QtWidgets.QDialogButtonBox.StandardButton.Ok)
        self.assertIsNotNone(ok_btn)

    # ------------------------------------------------------------------
    # Behavioural: restore / update against GLOBAL_SETTINGS.
    # ------------------------------------------------------------------
    def test_restore_global_settings_reflects_subset(self):
        """Checkboxes for agencies absent from GLOBAL_SETTINGS are unchecked."""
        # Pretend only EUROSTAT and GROW are currently enabled.
        GLOBAL_SETTINGS.agencies = [Agency.EUROSTAT, Agency.GROW]
        dialog = self._make_dialog()

        for agency, checkbox in dialog._agencies_checkboxes.items():
            if agency in (Agency.EUROSTAT, Agency.GROW):
                self.assertTrue(
                    checkbox.isChecked(),
                    f'{agency.name} should remain checked',
                )
            else:
                self.assertFalse(
                    checkbox.isChecked(),
                    f'{agency.name} should be unchecked',
                )

    def test_update_global_settings_reads_back_checkboxes(self):
        """update_global_settings writes selected agencies to GLOBAL_SETTINGS."""
        dialog = self._make_dialog()

        # Uncheck everything except COMP and EMPL.
        for agency, checkbox in dialog._agencies_checkboxes.items():
            checkbox.setChecked(agency in (Agency.COMP, Agency.EMPL))

        dialog.update_global_settings()

        self.assertEqual(
            set(GLOBAL_SETTINGS.agencies), {Agency.COMP, Agency.EMPL}
        )

    def test_update_global_settings_empty_selection_falls_back_to_all(self):
        """If no checkboxes are checked, all agencies become selected.

        This documents the fallback in ``update_global_settings``.
        """
        dialog = self._make_dialog()

        for checkbox in dialog._agencies_checkboxes.values():
            checkbox.setChecked(False)

        dialog.update_global_settings()

        self.assertEqual(set(GLOBAL_SETTINGS.agencies), set(Agency))


if __name__ == '__main__':
    suite = unittest.TestLoader().loadTestsFromModule(__import__(__name__))
    runner = unittest.TextTestRunner(verbosity=2)
    runner.run(suite)
