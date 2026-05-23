"""This script initializes the plugin, making it known to QGIS."""

from __future__ import annotations

from qgis.gui import QgisInterface

from eurostat_downloader.src.eurostat_downloader import EurostatDownloader


def classFactory(iface: QgisInterface) -> EurostatDownloader:
    """Load EurostatDownloader class from file EurostatDownloader.

    :param iface: A QGIS interface instance.
    :type iface: QgsInterface
    """
    return EurostatDownloader(iface)
