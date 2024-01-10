
from qgis.PyQt.QtWidgets import (
    QDialog
)

from .ui import EurostatDialogBase
from .eurostat_data import (
    EstatDatabase,
    EstatDataset
)

class EurostatDialog(QDialog):
    def __init__(self):
        super().__init__()
        ui = EurostatDialogBase()
        ui.setupUi(self)
        self.ui = ui
        self.database = EstatDatabase()
        
        # Signals
        self.ui.pbSearch.clicked.connect(self.populate_list)

    def populate_list(self):
        keyword = self.ui.searchDatabase.text()
        subset = self.database.get_subset(keyword)