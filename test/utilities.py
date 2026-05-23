# coding=utf-8
"""Common functionality used by regression tests."""

from __future__ import annotations

import logging

from processing.core.Processing import Processing
from qgis.PyQt import QtCore, QtWidgets
from qgis.PyQt.QtWidgets import QWidget
from qgis.core import QgsApplication
from qgis.gui import QgsMapCanvas

from test.qgis_interface import QgisInterface


LOGGER = logging.getLogger('QGIS')
QGIS_APP: QgsApplication | None = None
CANVAS: QgsMapCanvas | None = None
PARENT: QWidget | None = None
IFACE: QgisInterface | None = None


def get_qgis_app() -> tuple[QgsApplication, QgsMapCanvas, QgisInterface, QWidget]:
    """Start one QGIS application to test against.

    :returns: Handle to QGIS app, canvas, iface and parent.
    :rtype: (QgsApplication, QgsMapCanvas, QgisInterface, QWidget)

    If QGIS is already running the handle to that app will be returned.
    """
    global QGIS_APP  # pylint: disable=W0603

    if QGIS_APP is None:
        existing = QgsApplication.instance()
        if existing is not None:
            QGIS_APP = existing
        else:
            gui_flag = True
            QGIS_APP = QgsApplication([], gui_flag)
            QGIS_APP.initQgis()
        Processing.initialize()

    global PARENT  # pylint: disable=W0603
    if PARENT is None:
        PARENT = QtWidgets.QWidget()

    global CANVAS  # pylint: disable=W0603
    if CANVAS is None:
        CANVAS = QgsMapCanvas(PARENT)
        CANVAS.resize(QtCore.QSize(400, 400))

    global IFACE  # pylint: disable=W0603
    if IFACE is None:
        IFACE = QgisInterface(CANVAS)

    return QGIS_APP, CANVAS, IFACE, PARENT
