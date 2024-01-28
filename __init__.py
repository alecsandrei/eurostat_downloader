# -*- coding: utf-8 -*-
"""This script initializes the plugin, making it known to QGIS."""
import os
import site
import pkg_resources
import platform


def pre_init_plugin():
    # Taken from ee_plugin: https://github.com/gee-community/qgis-earthengine-plugin.
    if platform.system() == "Windows":
        extlib_path = "extlibs_windows"
#    if platform.system() == "Darwin":
#        extlib_path = "extlibs_darwin"
    if platform.system() == "Linux":
        extlib_path = "extlibs_linux"
    extra_libs_path = os.path.abspath(
        os.path.join(os.path.dirname(__file__), extlib_path)
    )

    # add to python path
    site.addsitedir(extra_libs_path)
    # pkg_resources doesn't listen to changes on sys.path.
    pkg_resources.working_set.add_entry(extra_libs_path)

# noinspection PyPep8Naming
def classFactory(iface):  # pylint: disable=invalid-name
    """Load EurostatDownloader class from file EurostatDownloader.

    :param iface: A QGIS interface instance.
    :type iface: QgsInterface
    """
    pre_init_plugin()
    from .eurostat_downloader import EurostatDownloader
    return EurostatDownloader(iface)
