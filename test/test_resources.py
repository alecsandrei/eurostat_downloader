# coding=utf-8
"""Resources test.

.. note:: This program is free software; you can redistribute it and/or modify
     it under the terms of the GNU General Public License as published by
     the Free Software Foundation; either version 2 of the License, or
     (at your option) any later version.

"""

from __future__ import annotations

__author__ = 'cuvuliucalexandrei@gmail.com'
__date__ = '2023-12-28'
__copyright__ = 'Copyright 2023, Cuvuliuc Alex-Andrei'

import unittest

from qgis.PyQt.QtGui import QIcon

from test.utilities import get_qgis_app

from eurostat_downloader import resources_rc  # noqa: F401

QGIS_APP, CANVAS, IFACE, PARENT = get_qgis_app()

from eurostat_downloader.src.eurostat_downloader import EurostatDownloader  # noqa: E402


class EurostatDownloaderDialogTest(unittest.TestCase):
    """Test rerources work."""

    def setUp(self) -> None:
        """Runs before each test."""
        pass

    def tearDown(self) -> None:
        """Runs after each test."""
        pass

    def test_icon_png(self) -> None:
        """Test we can click OK."""
        path = ':/plugins/eurostat_downloader/assets/icon.png'
        icon = QIcon(path)
        self.assertFalse(icon.isNull())

    def test_initgui_action_has_non_null_icon(self) -> None:
        """The QAction created by ``initGui`` must have a loaded icon."""
        plugin = EurostatDownloader(IFACE)
        try:
            plugin.initGui()
            self.assertGreaterEqual(len(plugin.actions), 1)
            self.assertFalse(plugin.actions[0].icon().isNull())
        finally:
            plugin.unload()


if __name__ == '__main__':
    suite = unittest.makeSuite(EurostatDownloaderDialogTest)
    runner = unittest.TextTestRunner(verbosity=2)
    runner.run(suite)
