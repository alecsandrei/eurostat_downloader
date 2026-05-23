# coding=utf-8
"""Common functionality used by regression tests."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from qgis.PyQt.QtWidgets import QWidget
    from qgis.core import QgsApplication
    from qgis.gui import QgsMapCanvas

    from test.qgis_interface import QgisInterface as QgisInterfaceStub


LOGGER = logging.getLogger('QGIS')
QGIS_APP: QgsApplication | None = None
CANVAS: QgsMapCanvas | None = None
PARENT: QWidget | None = None
IFACE: QgisInterfaceStub | None = None


def get_qgis_app() -> (
    tuple[QgsApplication, QgsMapCanvas, QgisInterfaceStub, QWidget]
    | tuple[None, None, None, None]
):
    """Start one QGIS application to test against.

    :returns: Handle to QGIS app, canvas, iface and parent. If there are any
        errors the tuple members will be returned as None.
    :rtype: (QgsApplication, CANVAS, IFACE, PARENT)

    If QGIS is already running the handle to that app will be returned.
    """

    try:
        from qgis.PyQt import QtCore, QtWidgets
        from qgis.core import QgsApplication
        from qgis.gui import QgsMapCanvas
        from test.qgis_interface import QgisInterface
    except ImportError:
        return None, None, None, None

    global QGIS_APP  # pylint: disable=W0603

    if QGIS_APP is None:
        existing = QgsApplication.instance()
        if existing is not None:
            QGIS_APP = existing
        else:
            gui_flag = True
            QGIS_APP = QgsApplication([], gui_flag)
            QGIS_APP.initQgis()

    global PARENT  # pylint: disable=W0603
    if PARENT is None:
        PARENT = QtWidgets.QWidget()

    global CANVAS  # pylint: disable=W0603
    if CANVAS is None:
        # noinspection PyPep8Naming
        CANVAS = QgsMapCanvas(PARENT)
        CANVAS.resize(QtCore.QSize(400, 400))

    global IFACE  # pylint: disable=W0603
    if IFACE is None:
        # QgisInterface is a stub implementation of the QGIS plugin interface
        # noinspection PyPep8Naming
        IFACE = QgisInterface(CANVAS)

    return QGIS_APP, CANVAS, IFACE, PARENT
