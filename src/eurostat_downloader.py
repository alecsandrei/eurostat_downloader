from __future__ import annotations

from dataclasses import (
    dataclass,
    field
)
from functools import cached_property
from typing import (
    Union,
    Iterable,
    Any
)

import pandas as pd
from qgis.PyQt import (
    QtCore,
    QtWidgets
)

from .ui import (
    UIDialog,
    UIParameterSectionDialog
)
from .eurostat_data import (
    Database,
    Dataset
)



@dataclass(slots=False, init=False)
class Dialog(QtWidgets.QDialog):
    ui: UIDialog = field(init=False)
    database: Database = field(init=False)
    dataset: Dataset = field(init=False)
    subset: pd.DataFrame = field(init=False)
    model: DatasetModel = field(init=False)
    filterer: DataFilterer = field(init=False)
    
    def __init__(self):
        super().__init__()
        self.database = Database()

        # Init GUI
        self.ui = UIDialog()
        self.ui.setupUi(self)

        # Signals
        self.ui.buttonSearch.clicked.connect(self.populate_list)
        self.ui.listDatabase.itemSelectionChanged.connect(self.set_dataset_table)
        self.ui.listDatabase.itemSelectionChanged.connect(self.set_table_join_fields)
        self.ui.tableDataset.horizontalHeader().sectionDoubleClicked.connect(self.open_section_ui)
        
    def populate_list(self):
        self.ui.listDatabase.clear()
        self.subset = self.database.get_subset(keyword=self.ui.lineSearch.text())
        titles = self.database.get_titles(subset=self.subset)
        codes = self.database.get_codes(subset=self.subset)
        self.ui.listDatabase.addItems('[' + codes + '] ' + titles)

    def get_selected_dataset_code(self):
        row = self.ui.listDatabase.currentRow()
        return self.database.get_codes(subset=self.subset).iloc[row]

    def get_current_table_join_field(self):
        return self.ui.comboTableJoinField.currentText()

    def set_table_join_fields(self):
        self.ui.comboTableJoinField.clear()
        self.ui.comboTableJoinField.addItems(self.dataset.params)

    def set_dataset_table(self):
        self.dataset = Dataset(db=self.database, code=self.get_selected_dataset_code())
        self.filterer = DataFilterer(df=self.dataset.df)
        self.update_model()

    def update_model(self):
        self.model = DatasetModel(estat_dataset=self.dataset, filterer=self.filterer)
        self.ui.tableDataset.setModel(self.model.pandas)

    def get_selected_section_name(self):
        clicked_section_index = self.ui.tableDataset.horizontalHeader().currentIndex().column()
        return self.dataset.df.columns[clicked_section_index]

    def open_section_ui(self):
        ParameterSectionDialog(name=self.get_selected_section_name(), base=self)


@dataclass(init=False)
class ParameterSectionDialog(QtWidgets.QDialog):
    
    def __init__(self, base: Dialog, name: str):
        super().__init__()
        self.base = base
        self.name = name
        self.ui = UIParameterSectionDialog()
        self.ui.setupUi(self)
        self.populate_list()
        self.section_type_handler()

        # Signals
        self.ui.lineSearch.textChanged.connect(self.filter_list_items)
        self.ui.buttonReset.clicked.connect(self.reset_selection)
        self.ui.listItems.itemSelectionChanged.connect(self.filter_table)
        
        self.exec_()
        
    def reset_selection(self):
        self.ui.listItems.clearSelection()

    def populate_list(self):
        self.ui.listItems.addItems(self.base.dataset.df[self.name].unique())

    def get_line_search_text(self):
        return self.ui.lineSearch.text()

    def filter_list_items(self):
        search_text = self.get_line_search_text()
        for row in range(self.ui.listItems.count()):
            item = self.ui.listItems.item(row)
            item_text = item.text().lower()
            item.setHidden(search_text not in item_text)

    def get_selected_items(self):
        return [item.text() for item in self.ui.listItems.selectedItems()]

    def section_type_handler(self):
        if self.name == (geo_field := self.base.get_current_table_join_field()):
            GeoParameterSectionDialog(section_dialog=self, name=geo_field)
    
    def filter_table(self):
        if self.name in self.base.filterer.filters:
            self.base.filterer.remove_filters(filters=self.name)
        if self.get_selected_items():
            self.base.filterer.add_filters(
                filters={self.name: self.get_selected_items()}
            )
        self.base.update_model()


@dataclass(init=False)
class GeoParameterSectionDialog:
    def __init__(self, section_dialog: ParameterSectionDialog, name: str):
        self.section_dialog = section_dialog
        self.name = name


@dataclass
class DataFilterer:
    df: pd.DataFrame
    filters: dict[str, list[Any]] = field(init=False, default_factory=dict)
    
    def apply_filters(self):
        """Source: https://stackoverflow.com/questions/34157811/filter-a-pandas-dataframe-using-values-from-a-dict"""
        if not self.filters:
            return self.df
        ind = [True] * len(self.df)
        for col, vals in self.filters.items():
            ind = ind & (self.df[col].isin(vals))
        return self.df[ind]
    
    def add_filters(self, filters: dict[str, Iterable[Any]]):
        for col, values in filters.items():
            for value in values:
                self.filters.setdefault(col, []).append(value)
    
    def remove_filters(self, filters: Union[str, dict[str, Iterable[Any]], list[str]]):
        if isinstance(filters, str):
            self.filters.pop(filters)
        if isinstance(filters, list):
            for filter_ in filters:
                self.filters.pop(filter_)
        if isinstance(filters, dict):
            for col, values in filters.items():
                for value in values:
                    self.filters[col].remove(value)
                if not self.filters[col]:
                    self.filters.pop(col)


@dataclass
class DatasetModel:
    estat_dataset: Dataset
    filterer: DataFilterer

    @property
    def pandas(self) -> PandasModel:
        return PandasModel(data=self.filterer.apply_filters())


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
