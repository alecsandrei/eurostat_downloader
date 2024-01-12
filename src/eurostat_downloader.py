from __future__ import annotations

from dataclasses import (
    dataclass,
    field
)
from functools import cached_property

import pandas as pd
from qgis.PyQt import (
    QtCore,
    QtWidgets
)

from .ui import (
    UIEurostatDialog,
    UIEurostatParameterSectionDialog
)
from .eurostat_data import (
    EstatDatabase,
    EstatDataset
)


@dataclass(slots=False, init=False)
class EurostatDialog(QtWidgets.QDialog):
    ui: UIEurostatDialog = field(init=False)
    database: EstatDatabase = field(init=False)
    dataset: EstatDataset = field(init=False)
    subset: pd.DataFrame = field(init=False)
    model: EstatDatasetModel = field(init=False)
    
    def __init__(self):
        super().__init__()
        self.ui = UIEurostatDialog()
        self.ui.setupUi(self)
        self.database = EstatDatabase()

        # Signals
        self.ui.buttonSearch.clicked.connect(self.populate_list)
        self.ui.listDatabase.itemSelectionChanged.connect(self.dataset_to_table)
        self.ui.tableDataset.horizontalHeader().sectionDoubleClicked.connect(self.open_section_ui)
        
    def populate_list(self):
        self.subset = self.database.get_subset(keyword=self.ui.lineSearch.text())
        titles = self.database.get_titles(subset=self.subset)
        codes = self.database.get_codes(subset=self.subset)
        self.ui.listDatabase.addItems('[' + codes + '] ' + titles)

    def get_selected_dataset_code(self):
        row = self.ui.listDatabase.currentRow()
        return self.database.get_codes(subset=self.subset).iloc[row]

    def dataset_to_table(self):
        self.dataset = EstatDataset(database=self.database, code=self.get_selected_dataset_code())
        self.model = EstatDatasetModel(estat_dataset=self.dataset, df=self.dataset.df)
        self.ui.tableDataset.setModel(self.model.pandas)

    def get_selected_section_name(self):
        clicked_section_index = self.ui.tableDataset.horizontalHeader().currentIndex().column()
        return self.model.df.columns[clicked_section_index]

    def open_section_ui(self):
        EurostatParameterSectionDialog(name=self.get_selected_section_name(), base=self)


@dataclass(init=False)
class EurostatParameterSectionDialog(QtWidgets.QDialog):
    
    def __init__(self, name: str, base: EurostatDialog):
        super().__init__()
        self.name = name
        self.base = base
        self.ui = UIEurostatParameterSectionDialog()
        self.ui.setupUi(self)
        self.populate_list()
        self.exec_()

    def populate_list(self):
        self.ui.listItems.addItems(self.base.model.df[self.name].unique())


@dataclass
class EstatDatasetModel:
    estat_dataset: EstatDataset
    df: pd.DataFrame
    
    @cached_property
    def pandas(self) -> PandasModel:
        return PandasModel(data=self.df)


class PandasModel(QtCore.QAbstractTableModel):
    """Class to turn a pandas dataframe into a QAbstractTableModel."""
    def __init__(self, data: pd.DataFrame, parent=None):
        QtCore.QAbstractTableModel.__init__(self, parent)
        self._data = data

    def rowCount(self, parent=None):
        return self._data.shape[0]

    def columnCount(self, parent=None):
        return self._data.shape[1]

    def data(self, index, role=QtCore.Qt.ItemDataRole.DisplayRole):
        if index.isValid():
            if role == QtCore.Qt.ItemDataRole.DisplayRole:
                return str(self._data.iloc[index.row(), index.column()])
        return None

    def headerData(self, col, orientation, role):
        if orientation == QtCore.Qt.Orientation.Horizontal and role == QtCore.Qt.ItemDataRole.DisplayRole:
            return self._data.columns[col]
        return None
