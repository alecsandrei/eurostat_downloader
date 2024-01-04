import os

from qgis.PyQt import uic
from qgis.PyQt import QtWidgets

FORM_CLASS, _ = uic.loadUiType(os.path.join(
    os.path.dirname(__file__), 'eurostat_downloader_dialog.ui'))


class EurostatDownloaderDialog(QtWidgets.QDialog, FORM_CLASS):
    def __init__(self, parent=None):
        super(EurostatDownloaderDialog, self).__init__(parent)
        self.setupUi(self)
