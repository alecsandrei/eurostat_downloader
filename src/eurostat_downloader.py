from __future__ import annotations

from dataclasses import (
    dataclass,
    field
)
from typing import (
    Union,
    Iterable,
    Any,
)

import numpy as np
import pandas as pd
from qgis.PyQt import (
    QtCore,
    QtWidgets
)

from .ui import (
    UIDialog,
    UIParameterSectionDialog,
    UITimePeriodDialog
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
        self.ui.tableDataset.horizontalHeader().sectionClicked.connect(self.open_section_ui)
        self.ui.buttonReset.clicked.connect(self.reset_dataset_table)
        
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
        self.filterer = DataFilterer(dataset=self.dataset)
        self.update_model()

    def update_model(self):
        self.model = DatasetModel(estat_dataset=self.dataset, filterer=self.filterer)
        self.ui.tableDataset.setModel(self.model.pandas)

    def open_section_ui(self, idx):
        section_name = self.dataset.df.columns[idx]
        if section_name in self.dataset.params:
            ParameterSectionDialog(base=self, name=section_name)
        elif section_name in self.dataset.date_columns:
            TimeSectionDialog(base=self, name=section_name)
            
    def reset_dataset_table(self):
        self.filterer.remove_row_filters()
        self.filterer.set_column_filters()
        self.update_model()


@dataclass(init=False)
class ParameterSectionDialog(QtWidgets.QDialog):
    
    def __init__(self, base: Dialog, name: str):
        super().__init__()
        self.base = base
        self.name = name
        self.ui = UIParameterSectionDialog()
        self.ui.setupUi(self)
        self.populate_list()
        self.select_based_on_filterer()
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

    def select_based_on_filterer(self):
        if self.name in self.base.filterer.row:
            for row in range(self.ui.listItems.count()):
                item = self.ui.listItems.item(row)
                item.setSelected(item.text() in self.base.filterer.row[self.name])

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
        if self.name in self.base.filterer.row:
            self.base.filterer.remove_row_filters(filters=self.name)
        if self.get_selected_items():
            self.base.filterer.add_row_filters(
                filters={self.name: self.get_selected_items()}
            )
        self.base.update_model()


@dataclass(init=False)
class GeoParameterSectionDialog:
    def __init__(self, section_dialog: ParameterSectionDialog, name: str):
        self.section_dialog = section_dialog
        self.name = name


@dataclass(init=False)
class TimeSectionDialog(QtWidgets.QDialog):
    def __init__(self, base: Dialog, name: str):
        super().__init__()
        self.base = base
        self.name = name
        self.ui = UITimePeriodDialog()
        self.ui.setupUi(self)
        self.add_widgets_to_frames()
        self.add_items_to_combobox()
        self.restore()
        # Signals
        self.add_signals_to_combobox()
        self.ui.buttonReset.clicked.connect(self.set_default)

        self.exec_()

    def get_time_types(self):
        freq = self.base.dataset.frequency.lower()
        if freq == 'a':
            return ['Year']
        elif freq == 's':
            return ['Year', 'Season']
        elif freq == 'q':
            return ['Year', 'Quarter']
        elif freq == 'm':
            return ['Year', 'Month']
        elif freq == 'd':
            return ['Year', 'Month', 'Day']
        else:
            raise Exception('No frequency column was found')
    
    def add_labels_to_frames(self, time: str):
        time = time.capitalize()
        label_object_name = ''.join(['label', time])
        self.ui.add_label_to_frames(object_name=label_object_name, text=time)
            
    def add_combobox_to_frames(self, time: str):
        time = time.capitalize()
        combo_object_name = ''.join(['combo', time])
        self.ui.add_combobox_to_frames(object_name=combo_object_name)
    
    def add_widgets_to_frames(self):
        for time in self.get_time_types():
            self.add_labels_to_frames(time=time)
            self.add_combobox_to_frames(time=time)

    def add_items_to_start_combobox(self):
        for idx, time in enumerate(self.get_time_types()):
            widget = self.ui.frameStart.findChild(QtWidgets.QComboBox, ''.join(['combo', time]))
            widget.addItems(self.base.dataset.date_columns
                            .str
                            .split('-')
                            .str
                            .get(idx)
                            .unique())

    def add_items_to_end_combobox(self):
        for idx, time in enumerate(self.get_time_types()):
            widget = self.ui.frameEnd.findChild(QtWidgets.QComboBox, ''.join(['combo', time]))
            items = self.base.dataset.date_columns.str.split('-').str.get(idx).unique()
            widget.addItems(items)
        
    def add_items_to_combobox(self):
        self.add_items_to_start_combobox()
        self.add_items_to_end_combobox()
    
    def add_signals_to_combobox(self):
        for frame in (self.ui.frameStart, self.ui.frameEnd):
            widgets = frame.findChildren(QtWidgets.QComboBox)
            for widget in widgets:
                widget.currentIndexChanged.connect(self.add_time_filters)
    
    def get_start_time_combobox(self):
        times = []
        for time in self.get_time_types():
            widget = self.ui.frameStart.findChild(QtWidgets.QComboBox, ''.join(['combo', time]))
            times.append(widget.currentText())
        return '-'.join(times)
    
    def get_end_time_combobox(self):
        times = []
        for time in self.get_time_types():
            widget = self.ui.frameEnd.findChild(QtWidgets.QComboBox, ''.join(['combo', time]))
            times.append(widget.currentText())
        return '-'.join(times)

    def add_time_filters(self):
        cols = self.base.dataset.date_columns.to_list()
        try:
            start = cols.index(self.get_start_time_combobox())
        except ValueError:
            start = 0
        try:
            end = cols.index(self.get_end_time_combobox())
        except ValueError:
            end = len(cols)-1
        cols_filtered = cols[start:end+1]
        cols = self.base.dataset.params + cols_filtered
        self.base.filterer.set_column_filters(filters=cols)
        self.base.update_model()
    
    def set_default_start_combobox(self):
        for idx, time in enumerate(self.get_time_types()):
            widget = self.ui.frameStart.findChild(QtWidgets.QComboBox, ''.join(['combo', time]))
            items = self.base.dataset.date_columns.str.split('-').str.get(idx)
            items_first = items[0]
            items_unique = items.unique()
            default_index = items_unique.to_list().index(items_first)
            widget.setCurrentIndex(default_index)
    
    def set_default_end_combobox(self):
        for idx, time in enumerate(self.get_time_types()):
            widget = self.ui.frameEnd.findChild(QtWidgets.QComboBox, ''.join(['combo', time]))
            items = self.base.dataset.date_columns.str.split('-').str.get(idx)
            items_last = items[-1]
            items_unique = items.unique()
            default_index = items_unique.to_list().index(items_last)
            widget.setCurrentIndex(default_index)
    
    def set_default(self):
        self.set_default_start_combobox()
        self.set_default_end_combobox()
        self.add_time_filters()

    def restore_start_combobox(self):
        for idx, time in enumerate(self.get_time_types()):
            widget = self.ui.frameStart.findChild(QtWidgets.QComboBox, ''.join(['combo', time]))
            items = get_combobox_items(combobox=widget)
            if items:
                idx = items.index(self.base.filterer.date_columns[0].split('-')[idx])
                widget.setCurrentIndex(idx)
    
    def restore_end_combobox(self):
        for idx, time in enumerate(self.get_time_types()):
            widget = self.ui.frameEnd.findChild(QtWidgets.QComboBox, ''.join(['combo', time]))
            items = get_combobox_items(combobox=widget)
            if items:
                idx = items.index(self.base.filterer.date_columns[-1].split('-')[idx])
                widget.setCurrentIndex(idx)

    def restore(self):
        self.restore_start_combobox()
        self.restore_end_combobox()


@dataclass
class DataFilterer:
    dataset: Dataset
    row: dict[str, list[Any]] = field(init=False, default_factory=dict)
    column: list[str] = field(init=False, default_factory=list)

    @property
    def df(self):
        return self.dataset.df

    @property
    def date_columns(self):
        return np.setdiff1d(self.column, self.dataset.params).tolist()

    def __post_init__(self):
        self.column = self.dataset.df.columns.to_list()

    def apply_filters(self):
        """Source: https://stackoverflow.com/questions/34157811/filter-a-pandas-dataframe-using-values-from-a-dict"""
        ind = [True] * len(self.df)
        for col, vals in self.row.items():
            if not vals:
                continue
            ind = ind & (self.df[col].isin(vals))
        return self.df.loc[ind, self.column]
    
    def add_row_filters(self, filters: dict[str, Iterable[Any]]):
        # This is only for the row axis
        for col, values in filters.items():
            for value in values:
                self.row.setdefault(col, []).append(value)
    
    def set_column_filters(self, filters: Union[None, str, Iterable[str]] = None):
        if filters is None:
            filters = self.dataset.df.columns.to_list()
        elif isinstance(filters, str):
            filters = [filters]
        self.column = list(filters)

    def remove_row_filters(self, filters: Union[None, str, dict[str, Iterable[Any]], Iterable[str]] = None):
        if filters is None:
            self.row = {}
        elif isinstance(filters, str):
            self.row[filters].clear()
        elif isinstance(filters, dict):
            for col, values in filters.items():
                for value in values:
                    self.row[col].remove(value)
                if not self.row[col]:
                    self.row[col].clear()
        elif isinstance(filters, Iterable):
            for filter_ in filters:
                self.row[filter_].clear()

    def remove_column_filters(self, filters: Union[str, Iterable[str]]):
        if isinstance(filters, str):
            self.column.remove(filters)
        elif isinstance(filters, Iterable):
            for filter_ in filters:
                self.column.remove(filter_)


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

def get_combobox_items(combobox: QtWidgets.QComboBox) -> list[str]:
    return [combobox.itemText(i) for i in range(combobox.count())]