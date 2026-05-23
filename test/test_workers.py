# coding=utf-8
"""Tests for the ``QThread`` worker subclasses in ``eurostat_downloader.py``.

The plugin offloads three blocking calls onto background threads so the UI
stays responsive while data is fetched. All three worker classes live near
the bottom of ``eurostat_downloader/src/eurostat_downloader.py``:

* ``GISCOYearHandler`` -- calls ``theme.get_years()`` and pushes the result
  into ``base.ui.comboBoxGISCOYear`` via ``addItems``.
* ``DatabaseInitializer`` -- clears ``base.ui.treeDatabase``, calls
  ``base.database.initialize_toc()``, then ``base.populate_tree(...)``.
  On any exception it emits the ``error_ocurred(Exception)`` signal
  (note the spelling -- it is ``error_ocurred`` in the source, not
  ``error_occurred``; the C++/Qt signal name string is ``errorOcurred``).
* ``DatasetInitializer`` -- calls ``base.dataset.initialize_data()``,
  rebuilds ``base.filterer`` as a ``DataFilterer``, and calls
  ``base.update_model()``. No error signal is exposed on this class.

What gets mocked
----------------
The natural test boundary is the data layer: ``Database.initialize_toc``,
``Dataset.initialize_data`` and ``GISCO.get_years`` are the methods that
would otherwise hit the Eurostat / GISCO HTTP endpoints. We swap them for
``MagicMock`` return values (synthetic strings / lists) so the workers
exercise their real ``run()`` bodies against in-process data only.

The ``Dialog`` parent is the second boundary. ``QThread.__init__`` takes
a ``QObject`` parent at the C++ layer, so we cannot pass a bare
``MagicMock`` (the C++ constructor would refuse it). Instead we build a
real ``QObject`` subclass (``_FakeDialog``) whose attributes are filled in
ad-hoc with ``MagicMock`` substitutes for ``ui``, ``database``,
``dataset``, ``populate_tree``, ``update_model``, etc. This keeps Qt
parentage happy while giving every attribute access a recordable mock.

Why ``worker.start()`` + ``worker.wait(ms)`` and not a QEventLoop
-----------------------------------------------------------------
The workers' ``run()`` bodies are short and synchronous once their
dependencies are mocked -- there is no async I/O left for an event loop
to pump. ``QThread.start()`` schedules ``run`` on a new OS thread;
``QThread.wait(ms)`` blocks until that thread terminates (or the timeout
expires). We use a generous 5000 ms ceiling so that if a worker ever did
deadlock the test would fail loudly rather than hang the suite.

Signals worth verifying
-----------------------
Only ``DatabaseInitializer`` exposes a Python signal (``error_ocurred``).
We verify two things about it: (a) it exists on the class as a
``pyqtSignal`` attribute, and (b) it actually fires with the exception
instance when ``initialize_toc`` raises. The other two workers expose no
signals, so we limit those tests to "mocked method was called once" plus
a structural QThread-subclass check.
"""

from __future__ import annotations

__author__ = 'cuvuliucalexandrei@gmail.com'
__date__ = '2026-05-23'

import unittest
from typing import cast
from unittest.mock import MagicMock, patch

from test.utilities import get_qgis_app

QGIS_APP, CANVAS, IFACE, PARENT = get_qgis_app()

from qgis.PyQt import QtCore  # noqa: E402

from eurostat_downloader.src.eurostat_downloader import (  # noqa: E402
    DatabaseInitializer,
    DatasetInitializer,
    Dialog,
    GISCOYearHandler,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


_WAIT_TIMEOUT_MS = 5000


class _FakeDialog(QtCore.QObject):  # type: ignore[misc]  # QObject is Any without stubs
    """Minimal real ``QObject`` that the workers can be parented to.

    ``QThread.__init__(parent)`` requires ``parent`` to be a real ``QObject``
    (or ``None``) at the C++ layer, so a bare ``MagicMock`` would be
    rejected. We instead subclass ``QObject`` and let callers attach
    whatever ``MagicMock`` attributes they need (``ui``, ``database``,
    ``dataset``, ``populate_tree``, ``update_model``) after construction.
    """

    def __init__(self) -> None:
        super().__init__()


def _make_base_for_database_initializer() -> _FakeDialog:
    """Build a fake dialog wired up for ``DatabaseInitializer``."""
    base = _FakeDialog()
    base.ui = MagicMock()
    base.database = MagicMock()
    base.database.toc = [{'title': 'fake'}]  # truthy -> populate_tree fires
    base.populate_tree = MagicMock()
    return base


def _make_base_for_dataset_initializer() -> _FakeDialog:
    """Build a fake dialog wired up for ``DatasetInitializer``."""
    base = _FakeDialog()
    base.dataset = MagicMock()
    base.update_model = MagicMock()
    # ``DatasetInitializer.run`` rebinds ``base.filterer`` itself; we still
    # initialize the attribute slot so attribute access is well defined.
    base.filterer = None
    return base


def _make_base_for_gisco_year_handler() -> _FakeDialog:
    """Build a fake dialog wired up for ``GISCOYearHandler``."""
    base = _FakeDialog()
    base.ui = MagicMock()
    return base


# ---------------------------------------------------------------------------
# 1. GISCOYearHandler
# ---------------------------------------------------------------------------


class TestGISCOYearHandler(unittest.TestCase):
    """``GISCOYearHandler.run`` calls ``theme.get_years`` and pushes the
    returned list onto ``base.ui.comboBoxGISCOYear``."""

    def test_is_qthread_subclass(self) -> None:
        """Structural: worker must inherit from ``QThread``."""
        self.assertTrue(issubclass(GISCOYearHandler, QtCore.QThread))

    def test_happy_path_calls_get_years_and_adds_items(self) -> None:
        """``run`` invokes ``theme.get_years()`` once and forwards the
        result to ``comboBoxGISCOYear.addItems``."""
        base = _make_base_for_gisco_year_handler()
        theme = MagicMock()
        theme.get_years.return_value = ['2020', '2021', '2022']

        worker = GISCOYearHandler(cast(Dialog, base), theme)
        worker.start()
        finished = worker.wait(_WAIT_TIMEOUT_MS)

        self.assertTrue(finished, 'worker.run() did not finish within timeout')
        theme.get_years.assert_called_once_with()
        base.ui.comboBoxGISCOYear.addItems.assert_called_once_with(
            ['2020', '2021', '2022']
        )

    def test_worker_holds_base_and_theme_references(self) -> None:
        """The worker exposes its inputs as ``self.base`` and ``self.theme``
        -- the rest of the codebase reads these (e.g. for re-runs)."""
        base = _make_base_for_gisco_year_handler()
        theme = MagicMock()
        theme.get_years.return_value = []

        worker = GISCOYearHandler(cast(Dialog, base), theme)

        self.assertIs(worker.base, base)
        self.assertIs(worker.theme, theme)


# ---------------------------------------------------------------------------
# 2. DatabaseInitializer
# ---------------------------------------------------------------------------


class TestDatabaseInitializer(unittest.TestCase):
    """``DatabaseInitializer.run`` clears the tree, calls
    ``database.initialize_toc()``, and (if the TOC is non-empty) calls
    ``populate_tree``. On any exception it emits ``error_ocurred``."""

    def test_is_qthread_subclass(self) -> None:
        """Structural: worker must inherit from ``QThread``."""
        self.assertTrue(issubclass(DatabaseInitializer, QtCore.QThread))

    def test_error_signal_exists_as_pyqtsignal(self) -> None:
        """``error_ocurred`` must be exposed as a class-level pyqtSignal
        (note the misspelling preserved from the source)."""
        self.assertTrue(hasattr(DatabaseInitializer, 'error_ocurred'))
        # ``pyqtSignal`` attributes are not instances of a public type we
        # can isinstance-check cleanly, but their class name is stable.
        self.assertEqual(
            type(DatabaseInitializer.error_ocurred).__name__,
            'pyqtSignal',
        )

    def test_happy_path_clears_tree_and_populates(self) -> None:
        """When ``initialize_toc`` succeeds and ``toc`` is non-empty,
        ``run`` clears the tree then forwards the TOC to ``populate_tree``."""
        base = _make_base_for_database_initializer()

        worker = DatabaseInitializer(cast(Dialog, base))
        worker.start()
        finished = worker.wait(_WAIT_TIMEOUT_MS)

        self.assertTrue(finished, 'worker.run() did not finish within timeout')
        base.ui.treeDatabase.clear.assert_called_once_with()
        base.database.initialize_toc.assert_called_once_with()
        base.populate_tree.assert_called_once_with(base.database.toc)

    def test_empty_toc_short_circuits_populate(self) -> None:
        """When ``database.toc`` is empty/falsy, ``populate_tree`` is
        skipped (the early ``return None`` branch)."""
        base = _make_base_for_database_initializer()
        base.database.toc = []  # falsy -> early return

        worker = DatabaseInitializer(cast(Dialog, base))
        worker.start()
        finished = worker.wait(_WAIT_TIMEOUT_MS)

        self.assertTrue(finished, 'worker.run() did not finish within timeout')
        base.database.initialize_toc.assert_called_once_with()
        base.populate_tree.assert_not_called()

    def test_error_path_emits_error_signal(self) -> None:
        """When ``initialize_toc`` raises, the worker catches it and
        emits ``error_ocurred`` with the exception instance."""
        base = _make_base_for_database_initializer()
        boom = Exception('boom')
        base.database.initialize_toc.side_effect = boom

        captured: list[Exception] = []

        worker = DatabaseInitializer(cast(Dialog, base))
        worker.error_ocurred.connect(lambda e: captured.append(e))
        worker.start()
        finished = worker.wait(_WAIT_TIMEOUT_MS)

        self.assertTrue(finished, 'worker.run() did not finish within timeout')
        # The signal is queued across threads; drain pending events so the
        # connected slot fires before we inspect ``captured``.
        QtCore.QCoreApplication.processEvents()

        self.assertEqual(len(captured), 1)
        self.assertIs(captured[0], boom)
        # populate_tree must NOT have been called on the error path.
        base.populate_tree.assert_not_called()

    def test_error_path_for_populate_tree_also_emits(self) -> None:
        """The try/except wraps the whole ``run`` body, so an exception
        from ``populate_tree`` is also funneled into ``error_ocurred``."""
        base = _make_base_for_database_initializer()
        bang = RuntimeError('populate failed')
        base.populate_tree.side_effect = bang

        captured: list[Exception] = []

        worker = DatabaseInitializer(cast(Dialog, base))
        worker.error_ocurred.connect(lambda e: captured.append(e))
        worker.start()
        finished = worker.wait(_WAIT_TIMEOUT_MS)

        self.assertTrue(finished, 'worker.run() did not finish within timeout')
        QtCore.QCoreApplication.processEvents()

        self.assertEqual(len(captured), 1)
        self.assertIs(captured[0], bang)


# ---------------------------------------------------------------------------
# 3. DatasetInitializer
# ---------------------------------------------------------------------------


class TestDatasetInitializer(unittest.TestCase):
    """``DatasetInitializer.run`` calls ``dataset.initialize_data()``,
    rebuilds ``base.filterer`` as a ``DataFilterer`` and triggers
    ``base.update_model()``."""

    def test_is_qthread_subclass(self) -> None:
        """Structural: worker must inherit from ``QThread``."""
        self.assertTrue(issubclass(DatasetInitializer, QtCore.QThread))

    def test_error_signal_exists_as_pyqtsignal(self) -> None:
        """``error_ocurred`` must be exposed as a class-level pyqtSignal
        so callers can connect a handler before ``start()``."""
        attr = vars(DatasetInitializer).get('error_ocurred')
        self.assertIsNotNone(attr)
        self.assertEqual(type(attr).__name__, 'pyqtSignal')

    def test_happy_path_initializes_dataset_and_updates_model(self) -> None:
        """``run`` must call ``dataset.initialize_data``, build a real
        ``DataFilterer`` on ``base.filterer``, then call ``update_model``."""
        base = _make_base_for_dataset_initializer()

        worker = DatasetInitializer(cast(Dialog, base))
        worker.start()
        finished = worker.wait(_WAIT_TIMEOUT_MS)

        self.assertTrue(finished, 'worker.run() did not finish within timeout')
        base.dataset.initialize_data.assert_called_once_with()
        base.update_model.assert_called_once_with()
        # ``run`` rebinds ``base.filterer = DataFilterer(dataset=...)``;
        # confirm something was assigned (and that it is not the original
        # ``None`` slot value).
        self.assertIsNotNone(base.filterer)

    def test_filterer_is_built_with_the_dataset(self) -> None:
        """The rebuilt ``filterer`` must be constructed against
        ``base.dataset`` -- patch the ``DataFilterer`` symbol used inside
        ``eurostat_downloader.py`` and inspect the call."""
        base = _make_base_for_dataset_initializer()

        with patch(
            'eurostat_downloader.src.eurostat_downloader.DataFilterer'
        ) as filterer_cls:
            filterer_cls.return_value = MagicMock(name='filterer_instance')
            worker = DatasetInitializer(cast(Dialog, base))
            worker.start()
            finished = worker.wait(_WAIT_TIMEOUT_MS)

        self.assertTrue(finished, 'worker.run() did not finish within timeout')
        filterer_cls.assert_called_once_with(dataset=base.dataset)
        self.assertIs(base.filterer, filterer_cls.return_value)

    def test_initialize_data_failure_emits_error_signal(self) -> None:
        """When ``initialize_data`` raises, the worker catches it and
        emits ``error_ocurred`` with the exception; ``update_model``
        must not run."""
        base = _make_base_for_dataset_initializer()
        boom = Exception('net down')
        base.dataset.initialize_data.side_effect = boom

        captured: list[Exception] = []

        worker = DatasetInitializer(cast(Dialog, base))
        worker.error_ocurred.connect(lambda e: captured.append(e))
        worker.start()
        finished = worker.wait(_WAIT_TIMEOUT_MS)

        self.assertTrue(finished, 'worker.run() did not finish within timeout')
        QtCore.QCoreApplication.processEvents()

        self.assertEqual(len(captured), 1)
        self.assertIs(captured[0], boom)
        base.dataset.initialize_data.assert_called_once_with()
        base.update_model.assert_not_called()


if __name__ == '__main__':
    suite = unittest.TestLoader().loadTestsFromModule(__import__(__name__))
    runner = unittest.TextTestRunner(verbosity=2)
    runner.run(suite)
