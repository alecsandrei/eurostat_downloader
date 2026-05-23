# coding=utf-8
"""Tests for the TOC disk-caching layer in ``eurostat_downloader.src.data``.

The PyQt6/QGIS-4 migration audit was static-grep only; the JSON-on-disk
table-of-contents cache (``assets/eurostat_cache/eurostat_toc_<YYYY-MM-DD>.json``)
was therefore left untested. This module fills that gap.

Test plan
---------
Cache behaviours covered:

* **Path construction** -- ``Database.__post_init__`` builds the cache path
  from ``PACKAGE_DIR.parent / 'assets' / 'eurostat_cache' /
  'eurostat_toc_<today>.json'``. We verify the date-templated filename and
  ensure the parent directory is created on construction.
* **Write path** (``Database.cache_toc``) -- a populated ``_toc`` is
  serialised as JSON with ``Agency.name`` / ``Language.name`` strings as keys
  and indented output.
* **Read path** (``Database._load_toc_from_cache``) -- the JSON is parsed
  back into a ``dict[Agency, dict[Language, list[...]]]`` with the enum keys
  correctly reconstructed via ``Agency[name]`` / ``Language[name]``.
* **Round-trip** -- writing then reading produces the same in-memory shape.
* **DEBUG gating** -- ``initialize_toc`` only consults the cache when
  ``data.DEBUG`` is truthy and the cache file already exists; with DEBUG off,
  fetching occurs and (per the current code) caching does NOT happen.

Failure modes considered:

* Missing cache file -> ``_load_toc_from_cache`` raises ``FileNotFoundError``
  (it does no existence guard internally; the guard lives in
  ``initialize_toc``).
* Malformed JSON -> ``_load_toc_from_cache`` raises ``json.JSONDecodeError``.
* Unknown enum name in cache -> raises ``KeyError`` during reconstruction.
* Date drift -> a future / past date in the filename yields a different
  ``_cache_path``; today's path is recomputed only on construction.

Critical isolation rule
-----------------------
No test is allowed to touch the real ``assets/eurostat_cache`` directory.
Each test class uses ``tempfile.TemporaryDirectory`` plus monkey-patching of
``data.PACKAGE_DIR`` (and/or direct override of ``db._cache_path`` after
construction) to redirect all I/O into the temp tree.
"""

from __future__ import annotations

__author__ = 'cuvuliucalexandrei@gmail.com'
__date__ = '2026-05-23'

import json
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

from test.utilities import get_qgis_app

QGIS_APP, CANVAS, IFACE, PARENT = get_qgis_app()

from eurostat_downloader.src import data as data_module
from eurostat_downloader.src.data import Database
from eurostat_downloader.src.enums import Agency, Language


# ---------------------------------------------------------------------------
# Synthetic fixtures
# ---------------------------------------------------------------------------
SYNTHETIC_TOC_ROWS = [
    {'code': 'A', 'title': 'Category A', 'level': 0, 'type': 'folder'},
    {'code': 'A1', 'title': 'Dataset A1', 'level': 1, 'type': 'dataset'},
]


def _make_synthetic_toc():
    """Return a fresh ``_toc`` dict matching ``TableOfContents`` shape."""
    return {
        Agency.EUROSTAT: {
            Language.ENGLISH: [dict(row) for row in SYNTHETIC_TOC_ROWS],
        }
    }


def _make_synthetic_cache_json():
    """Return the on-disk JSON representation of the synthetic TOC."""
    return {
        Agency.EUROSTAT.name: {
            Language.ENGLISH.name: [dict(row) for row in SYNTHETIC_TOC_ROWS],
        }
    }


class _TempCacheMixin:
    """Mixin providing a temp dir that mimics ``PACKAGE_DIR.parent`` layout.

    Sets ``self.tmp_root`` (acts as ``PACKAGE_DIR.parent``) and
    ``self.fake_package_dir`` (acts as ``PACKAGE_DIR``) so that
    ``PACKAGE_DIR.parent / 'assets' / 'eurostat_cache'`` lands inside the
    temp tree. The ``assets`` dir is pre-created because the production
    code uses ``mkdir(exist_ok=True)`` without ``parents=True``.
    """

    def _setup_temp_cache(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp_root = Path(self._tmp.name)
        self.fake_package_dir = self.tmp_root / 'eurostat_downloader'
        self.fake_package_dir.mkdir()
        (self.tmp_root / 'assets').mkdir()


class TestTocCachePath(_TempCacheMixin, unittest.TestCase):
    """Path-construction behaviour of ``Database.__post_init__``."""

    def setUp(self):
        self._setup_temp_cache()

    def test_cache_path_uses_today_date(self):
        """Filename is templated with today's date in ISO-8601 form."""
        fixed_today = datetime(2026, 5, 23, 12, 0, 0)
        mock_dt = MagicMock()
        mock_dt.today.return_value = fixed_today
        with patch.object(data_module, 'PACKAGE_DIR', self.fake_package_dir), \
                patch.object(data_module, 'datetime', mock_dt):
            db = Database()
        self.assertEqual(
            db._cache_path.name, 'eurostat_toc_2026-05-23.json'
        )

    def test_cache_path_parent_is_created(self):
        """``__post_init__`` ensures the ``eurostat_cache`` dir exists."""
        cache_dir = self.tmp_root / 'assets' / 'eurostat_cache'
        self.assertFalse(cache_dir.exists())
        with patch.object(data_module, 'PACKAGE_DIR', self.fake_package_dir):
            db = Database()
        self.assertTrue(cache_dir.exists())
        self.assertEqual(db._cache_path.parent, cache_dir)

    def test_cache_path_under_package_parent(self):
        """Cache lives under ``PACKAGE_DIR.parent/assets/eurostat_cache``."""
        with patch.object(data_module, 'PACKAGE_DIR', self.fake_package_dir):
            db = Database()
        self.assertEqual(
            db._cache_path.parent,
            self.tmp_root / 'assets' / 'eurostat_cache',
        )


class TestTocCacheWrite(_TempCacheMixin, unittest.TestCase):
    """``Database.cache_toc`` serialisation behaviour."""

    def setUp(self):
        self._setup_temp_cache()
        with patch.object(data_module, 'PACKAGE_DIR', self.fake_package_dir):
            self.db = Database()

    def test_cache_write_serializes_toc_to_json(self):
        """A populated ``_toc`` round-trips into a JSON file with enum names."""
        self.db._toc = _make_synthetic_toc()
        self.db.cache_toc()

        self.assertTrue(self.db._cache_path.exists())
        with open(self.db._cache_path, encoding='utf-8') as f:
            raw = f.read()
        # Indent=2 produces newlines; sanity-check pretty-printing.
        self.assertIn('\n', raw)

        parsed = json.loads(raw)
        self.assertIn(Agency.EUROSTAT.name, parsed)
        self.assertIn(
            Language.ENGLISH.name, parsed[Agency.EUROSTAT.name]
        )
        rows = parsed[Agency.EUROSTAT.name][Language.ENGLISH.name]
        self.assertEqual(rows, SYNTHETIC_TOC_ROWS)

    def test_cache_write_empty_toc_produces_empty_object(self):
        """An empty ``_toc`` writes a valid empty-dict JSON file."""
        self.db._toc = {}
        self.db.cache_toc()
        with open(self.db._cache_path, encoding='utf-8') as f:
            parsed = json.load(f)
        self.assertEqual(parsed, {})

    def test_cache_write_overwrites_existing_file(self):
        """Writing replaces any prior contents at the cache path."""
        self.db._cache_path.write_text('stale garbage', encoding='utf-8')
        self.db._toc = _make_synthetic_toc()
        self.db.cache_toc()
        with open(self.db._cache_path, encoding='utf-8') as f:
            parsed = json.load(f)
        self.assertIn(Agency.EUROSTAT.name, parsed)


class TestTocCacheRead(_TempCacheMixin, unittest.TestCase):
    """``Database._load_toc_from_cache`` deserialisation behaviour."""

    def setUp(self):
        self._setup_temp_cache()
        with patch.object(data_module, 'PACKAGE_DIR', self.fake_package_dir):
            self.db = Database()

    def _write_cache(self, payload):
        with open(self.db._cache_path, 'w', encoding='utf-8') as f:
            json.dump(payload, f)

    def test_cache_read_reconstructs_enum_keys(self):
        """JSON string keys become ``Agency`` / ``Language`` enum members."""
        self._write_cache(_make_synthetic_cache_json())
        self.db._load_toc_from_cache()

        self.assertIn(Agency.EUROSTAT, self.db._toc)
        self.assertIn(Language.ENGLISH, self.db._toc[Agency.EUROSTAT])
        rows = self.db._toc[Agency.EUROSTAT][Language.ENGLISH]
        self.assertEqual(rows, SYNTHETIC_TOC_ROWS)

    def test_cache_read_missing_file_raises_file_not_found(self):
        """Reading a non-existent cache file raises ``FileNotFoundError``.

        The production code does not guard inside ``_load_toc_from_cache``;
        existence is checked by the caller (``initialize_toc``).
        """
        self.assertFalse(self.db._cache_path.exists())
        with self.assertRaises(FileNotFoundError):
            self.db._load_toc_from_cache()

    def test_cache_read_malformed_json_raises(self):
        """Malformed JSON propagates ``json.JSONDecodeError``."""
        self.db._cache_path.write_text('{not valid json', encoding='utf-8')
        with self.assertRaises(json.JSONDecodeError):
            self.db._load_toc_from_cache()

    def test_cache_read_unknown_agency_raises_key_error(self):
        """Unknown enum names cause a ``KeyError`` during reconstruction."""
        self._write_cache(
            {'NOT_AN_AGENCY': {Language.ENGLISH.name: []}}
        )
        with self.assertRaises(KeyError):
            self.db._load_toc_from_cache()

    def test_cache_read_unknown_language_raises_key_error(self):
        self._write_cache(
            {Agency.EUROSTAT.name: {'NOT_A_LANG': []}}
        )
        with self.assertRaises(KeyError):
            self.db._load_toc_from_cache()

    def test_cache_round_trip(self):
        """Write then read yields the original in-memory structure."""
        self.db._toc = _make_synthetic_toc()
        self.db.cache_toc()

        # Fresh DB pointed at the same cache file.
        with patch.object(data_module, 'PACKAGE_DIR', self.fake_package_dir):
            other = Database()
        other._cache_path = self.db._cache_path
        other._load_toc_from_cache()

        self.assertEqual(other._toc, _make_synthetic_toc())


class TestTocCacheDebugGating(_TempCacheMixin, unittest.TestCase):
    """``Database.initialize_toc`` interaction with the ``DEBUG`` flag."""

    def setUp(self):
        self._setup_temp_cache()
        with patch.object(data_module, 'PACKAGE_DIR', self.fake_package_dir):
            self.db = Database()

    def test_debug_mode_loads_from_cache_when_exists(self):
        """With DEBUG on and a cache file present, ``initialize_toc`` reads it.

        Network fetches must NOT happen in this code path; we assert by
        patching ``fetch.get_toc`` to a sentinel that would fail the test if
        called.
        """
        # Pre-populate the cache file.
        with open(self.db._cache_path, 'w', encoding='utf-8') as f:
            json.dump(_make_synthetic_cache_json(), f)

        fake_fetch = MagicMock(
            side_effect=AssertionError('fetch.get_toc must not be called')
        )
        with patch.object(data_module, 'DEBUG', True), \
                patch.object(data_module.fetch, 'get_toc', fake_fetch):
            self.db.initialize_toc()

        fake_fetch.assert_not_called()
        self.assertIn(Agency.EUROSTAT, self.db._toc)
        self.assertEqual(
            self.db._toc[Agency.EUROSTAT][Language.ENGLISH],
            SYNTHETIC_TOC_ROWS,
        )

    def test_debug_mode_writes_cache_when_missing(self):
        """With DEBUG on but no cache file, fetches run and write_cache happens."""
        self.assertFalse(self.db._cache_path.exists())

        fake_fetch = MagicMock(return_value=list(SYNTHETIC_TOC_ROWS))
        with patch.object(data_module, 'DEBUG', True), \
                patch.object(data_module.fetch, 'get_toc', fake_fetch):
            self.db.initialize_toc()

        self.assertTrue(fake_fetch.called)
        self.assertTrue(
            self.db._cache_path.exists(),
            'DEBUG+missing cache should trigger cache_toc()',
        )
        with open(self.db._cache_path, encoding='utf-8') as f:
            on_disk = json.load(f)
        # Every (language, agency) pair attempted should have produced a key.
        self.assertIn(Agency.EUROSTAT.name, on_disk)

    def test_non_debug_does_not_write_cache(self):
        """With DEBUG off, fetches run but no cache file is written."""
        self.assertFalse(self.db._cache_path.exists())

        fake_fetch = MagicMock(return_value=list(SYNTHETIC_TOC_ROWS))
        with patch.object(data_module, 'DEBUG', False), \
                patch.object(data_module.fetch, 'get_toc', fake_fetch):
            self.db.initialize_toc()

        self.assertTrue(fake_fetch.called)
        self.assertFalse(
            self.db._cache_path.exists(),
            'Non-DEBUG mode must not write a cache file',
        )

    def test_non_debug_ignores_existing_cache(self):
        """With DEBUG off, an existing cache file is not consulted."""
        # Pre-populate a sentinel cache that, if loaded, would set _toc.
        with open(self.db._cache_path, 'w', encoding='utf-8') as f:
            json.dump(
                {
                    Agency.EUROSTAT.name: {
                        Language.ENGLISH.name: [
                            {
                                'code': 'FROM_CACHE',
                                'title': 'should not appear',
                            }
                        ]
                    }
                },
                f,
            )

        fetched_rows = [{'code': 'FROM_FETCH', 'title': 'fresh'}]
        fake_fetch = MagicMock(return_value=list(fetched_rows))
        with patch.object(data_module, 'DEBUG', False), \
                patch.object(data_module.fetch, 'get_toc', fake_fetch):
            self.db.initialize_toc()

        # Network path was taken.
        self.assertTrue(fake_fetch.called)
        # _toc reflects fetched rows, not the cached sentinel.
        rows = self.db._toc[Agency.EUROSTAT][Language.ENGLISH]
        self.assertEqual([r['code'] for r in rows], ['FROM_FETCH'])


if __name__ == '__main__':
    suite = unittest.TestLoader().loadTestsFromModule(__import__(__name__))
    runner = unittest.TextTestRunner(verbosity=2)
    runner.run(suite)
