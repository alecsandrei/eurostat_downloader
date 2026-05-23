# coding=utf-8
"""QGIS plugin implementation.

.. note:: This program is free software; you can redistribute it and/or modify
     it under the terms of the GNU General Public License as published by
     the Free Software Foundation; either version 2 of the License, or
     (at your option) any later version.

.. note:: This source code was copied from the 'postgis viewer' application
     with original authors:
     Copyright (c) 2010 by Ivan Mincik, ivan.mincik@gista.sk
     Copyright (c) 2011 German Carrillo, geotux_tuxman@linuxmail.org
     Copyright (c) 2014 Tim Sutton, tim@linfiniti.com

"""

__author__ = 'tim@linfiniti.com'
__revision__ = '$Format:%H$'
__date__ = '10/01/2011'
__copyright__ = (
    'Copyright (c) 2010 by Ivan Mincik, ivan.mincik@gista.sk and '
    'Copyright (c) 2011 German Carrillo, geotux_tuxman@linuxmail.org'
    'Copyright (c) 2014 Tim Sutton, tim@linfiniti.com'
)

import logging
from qgis.PyQt.QtCore import QObject, pyqtSignal
from qgis.core import QgsProject

LOGGER = logging.getLogger('QGIS')


# noinspection PyMethodMayBeStatic,PyPep8Naming
class QgisInterface(QObject):
    """Class to expose QGIS objects and functions to plugins.

    This class is here for enabling us to run unit tests only,
    so most methods are simply stubs.
    """

    currentLayerChanged = pyqtSignal()

    def __init__(self, canvas):
        """Constructor
        :param canvas:
        """
        QObject.__init__(self)
        self.canvas = canvas
        self.destCrs = None

    def addLayers(self, layers):
        """No-op stub kept for API compatibility."""
        pass

    def addLayer(self, layer):
        """No-op stub kept for API compatibility."""
        pass

    def removeAllLayers(self):
        """Remove all layers from the project."""
        QgsProject.instance().removeAllMapLayers()

    def newProject(self):
        """Create new project."""
        QgsProject.instance().removeAllMapLayers()

    # ---------------- API Mock for QgsInterface follows -------------------

    def zoomFull(self):
        """Zoom to the map full extent."""
        pass

    def zoomToPrevious(self):
        """Zoom to previous view extent."""
        pass

    def zoomToNext(self):
        """Zoom to next view extent."""
        pass

    def zoomToActiveLayer(self):
        """Zoom to extent of active layer."""
        pass

    def addVectorLayer(self, path, base_name, provider_key):
        """Add a vector layer.

        :param path: Path to layer.
        :type path: str

        :param base_name: Base name for layer.
        :type base_name: str

        :param provider_key: Provider key e.g. 'ogr'
        :type provider_key: str
        """
        pass

    def addRasterLayer(self, path, base_name):
        """Add a raster layer given a raster layer file name

        :param path: Path to layer.
        :type path: str

        :param base_name: Base name for layer.
        :type base_name: str
        """
        pass

    def activeLayer(self):
        """Get pointer to the active layer (layer selected in the legend)."""
        layers = QgsProject.instance().mapLayers()
        for item in layers:
            return layers[item]

    def addToolBarIcon(self, action):
        """Add an icon to the plugins toolbar."""
        pass

    def removeToolBarIcon(self, action):
        """Remove an action (icon) from the plugin toolbar."""
        pass

    def addPluginToMenu(self, name, action):
        """Add an action to the plugins menu."""
        pass

    def removePluginMenu(self, name, action):
        """Remove an action from the plugins menu."""
        pass

    def addToolBar(self, name):
        """Add toolbar with specified name.

        :param name: Name for the toolbar.
        :type name: str
        """
        pass

    def mapCanvas(self):
        """Return a pointer to the map canvas."""
        return self.canvas

    def mainWindow(self):
        """Return a pointer to the main window.

        In case of QGIS it returns an instance of QgisApp.
        """
        pass

    def addDockWidget(self, area, dock_widget):
        """Add a dock widget to the main window.

        :param area: Where in the ui the dock should be placed.
        :type area:

        :param dock_widget: A dock widget to add to the UI.
        :type dock_widget: QDockWidget
        """
        pass

    def legendInterface(self):
        """Get the legend."""
        return self.canvas
