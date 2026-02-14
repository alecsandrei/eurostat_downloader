"""This script initializes the plugin, making it known to QGIS."""


def classFactory(iface):
    """Load EurostatDownloader class from file EurostatDownloader.

    :param iface: A QGIS interface instance.
    :type iface: QgsInterface
    """
    from .src.eurostat_downloader import EurostatDownloader

    return EurostatDownloader(iface)
