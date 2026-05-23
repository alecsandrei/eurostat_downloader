# coding=utf-8
"""Tests for the hand-written ``LoadingDialog`` UI component.

Test plan
---------
Component under test:
``eurostat_downloader.src.eurostat_downloader.LoadingDialog``.

What LoadingDialog does
~~~~~~~~~~~~~~~~~~~~~~~
A tiny modal-style ``QDialog`` shown while the plugin performs blocking work
(database/TOC initialization, dataset fetch, etc.). It is a single centered
``QLabel`` (``self.qlabel``) inside a ``QVBoxLayout``. The label text is
updated from the outside via ``update_loading_label(text)``; there is no
spinner widget, no progress bar, and no built-in button -- the caller is
expected to ``show()`` / ``close()`` the dialog around the work.

Construction paths
~~~~~~~~~~~~~~~~~~
Single ``__init__(self, base=None)`` -- ``base`` is the parent widget
(typically the main ``Dialog``) and is passed to ``QDialog.__init__`` and
also stashed on ``self.base``. Construction does NOT call ``self.exec()``
or ``self.show()``, so a plain instantiation under a unit test is safe and
non-blocking (no patching required).

What could break under PyQt6 (hand-written, not generated)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Unlike the other dialogs in this plugin (which come from ``.ui`` files run
through ``pyuic``), ``LoadingDialog.__init__`` is hand-written Python. The
PyQt5 -> PyQt6 migration risk here is whoever ported the constructor had
to remember to write *scoped* enum forms by hand. Looking at the current
source:

* ``layout.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)`` -- scoped
  form, PyQt6-correct. (PyQt5 would have accepted ``QtCore.Qt.AlignCenter``.)
* ``self.qlabel.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)`` -- ditto.

No ``QSizePolicy``, ``QFrame.Shape``, ``QFrame.Shadow``, ``QDialogButtonBox``
or modality enums are touched in this constructor, so the hand-written
unscoped-enum risk surface is actually narrower here than in the generated
dialogs -- which is a worthwhile finding in itself. The test below still
exercises construction so any future addition of an unscoped enum
(``QSizePolicy.Minimum``, ``QFrame.HLine``, ``Qt.WindowModal``, ...) trips
``test_constructs_without_error`` immediately.

Valuable assertions beyond "doesn't raise"
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
* Instance type is ``QDialog`` and ``self.base`` points back at the parent
  passed in (used by callers that want to re-parent or theme the dialog).
* The dialog owns a real ``QLabel`` accessible as ``self.qlabel``.
* The layout is a ``QVBoxLayout`` and contains the label.
* The label alignment is ``AlignCenter`` (verifies the scoped-enum value
  actually round-trips through Qt, not just that the attribute exists).
* ``update_loading_label`` mutates ``self.qlabel.text()`` -- the only public
  behavior method on the class.
* Construction works both with and without a parent (``base=None``).

What is intentionally NOT tested
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
* Modality / window flags -- the constructor does not set them, so any
  assertion would just lock in framework defaults.
* ``exec()`` / ``show()`` behavior -- those are caller responsibilities
  and would block the test runner.
* Font metrics / pixel sizes -- brittle across platforms and Qt versions.
* Visual appearance / paint events.
"""

__author__ = 'cuvuliucalexandrei@gmail.com'
__date__ = '2026-05-23'

import unittest

from qgis.PyQt import QtCore, QtWidgets

from eurostat_downloader.src.eurostat_downloader import LoadingDialog
from test.utilities import get_qgis_app

QGIS_APP, CANVAS, IFACE, PARENT = get_qgis_app()


class TestLoadingDialog(unittest.TestCase):
    """Test the hand-written LoadingDialog construction and public API."""

    def setUp(self):
        """Build a fresh LoadingDialog for each test."""
        self.parent = QtWidgets.QWidget()
        self.dialog = LoadingDialog(self.parent)

    def tearDown(self):
        """Release Qt objects so they don't leak between tests."""
        self.dialog.deleteLater()
        self.dialog = None
        self.parent.deleteLater()
        self.parent = None

    def test_constructs_without_error(self):
        """LoadingDialog instantiates without raising.

        Regression guard for the PyQt6 unscoped-enum class of bug. The
        hand-written constructor uses ``QtCore.Qt.AlignmentFlag.AlignCenter``
        (the scoped form). If somebody re-introduces an unscoped enum --
        ``QtCore.Qt.AlignCenter``, ``QSizePolicy.Minimum``, ``QFrame.HLine``
        etc. -- ``__init__`` will raise ``AttributeError`` here.
        """
        self.assertIsInstance(self.dialog, QtWidgets.QDialog)
        # The dialog stashes its parent under ``base`` for later access.
        self.assertIs(self.dialog.base, self.parent)

    def test_constructs_without_parent(self):
        """LoadingDialog also constructs with ``base=None`` (the default)."""
        dlg = LoadingDialog()
        try:
            self.assertIsInstance(dlg, QtWidgets.QDialog)
            self.assertIsNone(dlg.base)
        finally:
            dlg.deleteLater()

    def test_layout_and_label_present(self):
        """The dialog owns a QVBoxLayout containing a centered QLabel.

        Catches regressions where ``self.qlabel`` is renamed/removed or
        the layout class changes -- callers reach into ``self.qlabel``
        and ``self.layout()`` so both names are part of the public API.
        """
        self.assertIsInstance(self.dialog.layout(), QtWidgets.QVBoxLayout)
        self.assertIsInstance(self.dialog.qlabel, QtWidgets.QLabel)
        # Label is actually parented into the layout, not just hanging off
        # the dialog as an orphan attribute.
        self.assertIs(self.dialog.qlabel.parent(), self.dialog)
        self.assertEqual(self.dialog.layout().count(), 1)
        self.assertIs(
            self.dialog.layout().itemAt(0).widget(), self.dialog.qlabel
        )

    def test_label_alignment_is_center(self):
        """The label alignment is the scoped ``AlignCenter`` value.

        Verifies the scoped-enum value round-trips through Qt rather than
        only that the attribute lookup succeeded at construction time.
        """
        self.assertEqual(
            self.dialog.qlabel.alignment(),
            QtCore.Qt.AlignmentFlag.AlignCenter,
        )

    def test_update_loading_label_changes_text(self):
        """``update_loading_label`` mutates the QLabel text.

        This is the only public behavior method on ``LoadingDialog``.
        """
        # Starts empty -- the constructor never calls setText.
        self.assertEqual(self.dialog.qlabel.text(), '')

        self.dialog.update_loading_label('Initializing TOC...')
        self.assertEqual(self.dialog.qlabel.text(), 'Initializing TOC...')

        # Subsequent calls overwrite rather than append.
        self.dialog.update_loading_label('Fetching dataset...')
        self.assertEqual(self.dialog.qlabel.text(), 'Fetching dataset...')


if __name__ == '__main__':
    suite = unittest.TestLoader().loadTestsFromModule(__import__(__name__))
    runner = unittest.TextTestRunner(verbosity=2)
    runner.run(suite)
