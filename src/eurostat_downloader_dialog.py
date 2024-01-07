from pathlib import Path

from qgis.PyQt import uic
from qgis.PyQt.QtWidgets import (
    QDialog,
    QPushButton
)

UI = (Path(__file__).parent / 'eurostat_downloader_dialog.ui').as_posix()


class EurostatDownloaderDialog(QDialog):
    def __init__(self):
        super().__init__()
        uic.loadUi(UI, self)
