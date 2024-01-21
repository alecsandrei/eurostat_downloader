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
from enum import Enum

import numpy as np
import pandas as pd
from qgis.PyQt import (
    QtCore,
    QtWidgets
)
from qgis.core import (
    QgsVectorLayer,
    QgsField,
    QgsFeature,
    QgsProject,
    QgsVectorLayerJoinInfo,
    QgsMapLayer,
)
from .ui import (
    UIDialog,
    UIParameterSectionDialog,
    UITimePeriodDialog
)
from .eurostat_data import (
    Database,
    Dataset,
    Language
)



@dataclass(slots=False, init=False)
class Dialog(QtWidgets.QDialog):
    ui: UIDialog = field(init=False)
    database: Database = field(init=False)
    dataset: Dataset = field(init=False)
    subset: pd.DataFrame = field(init=False)
    model: DatasetModel = field(init=False)
    filterer: DataFilterer = field(init=False)
    join_handler: JoinHandler = field(init=False)
    exporter: Exporter = field(init=False)
    converter: QgsConverter = field(init=False)
    
    def __init__(self):
        super().__init__()

        # Init GUI
        self.ui = UIDialog()
        self.ui.setupUi(self)
        self.set_layer_join_fields()

        # Instantiate objects
        self.database = Database()
        self.join_handler = JoinHandler(base=self)
        self.exporter = Exporter(base=self)
        self.converter = QgsConverter(base=self)

        # Signals
        self.ui.qgsComboLayer.layerChanged.connect(self.set_layer_join_fields)
        self.ui.qgsComboLayer.layerChanged.connect(self.set_layer_join_field_default)
        self.ui.lineSearch.textChanged.connect(self.populate_list)
        self.ui.listDatabase.itemSelectionChanged.connect(self.set_dataset_table)
        self.ui.listDatabase.itemSelectionChanged.connect(self.set_table_join_fields)
        self.ui.listDatabase.itemSelectionChanged.connect(self.set_table_join_field_default)
        self.ui.listDatabase.itemSelectionChanged.connect(self.set_layer_join_field_default)
        self.ui.tableDataset.horizontalHeader().sectionClicked.connect(self.open_section_ui)
        self.ui.buttonReset.clicked.connect(self.reset_dataset_table)
        self.ui.buttonAdd.clicked.connect(self.exporter.add_table)
        self.ui.buttonJoin.clicked.connect(self.join_handler.join_table_to_layer)
        for language_check in (self.ui.checkEnglish, self.ui.checkGerman, self.ui.checkFrench):
            language_check.stateChanged.connect(self.update_language_check)

    def set_layer_join_fields(self):
        layer = self.ui.qgsComboLayer.currentLayer()
        if not layer:
            return
        self.ui.qgsComboLayerJoinField.setLayer(layer=layer)

    def populate_list(self):
        self.ui.listDatabase.clear()
        self.subset = self.database.get_subset(keyword=self.ui.lineSearch.text())
        titles = self.database.get_titles(subset=self.subset)
        codes = self.database.get_codes(subset=self.subset)
        items = '[' + codes + '] ' + titles
        self.ui.listDatabase.addItems(items)

    def get_selected_dataset_code(self):
        row = self.ui.listDatabase.currentRow()
        return self.database.get_codes(subset=self.subset).iloc[row]

    def get_current_table_join_field(self):
        return self.ui.comboTableJoinField.currentText()

    def update_language_check(self):
        language_checks = [self.ui.checkEnglish, self.ui.checkFrench, self.ui.checkGerman]
        if self.sender().isChecked():
            language_checks.remove(self.sender())
            for check in language_checks:
                check.setChecked(False)
        self.dataset.set_language(lang=self.get_selected_language())

    def get_selected_language(self):
        if self.ui.checkEnglish.isChecked():
            return Language.ENGLISH
        elif self.ui.checkFrench.isChecked():
            return Language.FRENCH
        elif self.ui.checkGerman.isChecked():
            return Language.GERMAN

    def set_table_join_fields(self):
        self.ui.comboTableJoinField.clear()
        self.ui.comboTableJoinField.addItems(self.dataset.params)

    def set_table_join_field_default(self):
        items = get_combobox_items(self.ui.comboTableJoinField)
        for idx, item in enumerate(items):
            if item in CommonGeoSectionNames:
                self.ui.comboTableJoinField.setCurrentIndex(idx)

    def infer_join_field_idx_from_layer(self, layer: QgsMapLayer):
        if layer.featureCount() > 100_000:
            # Don't infer join field if there are more than 100k features.
            return
        df = self.converter.to_dataframe(layer=layer)
        geo = self.ui.comboTableJoinField.currentText()
        unique_values = self.model.pandas._data[geo].unique()
        columns = df.columns[df.isin(unique_values).any()]
        if not columns.empty:
            idx = df.columns.to_list().index(columns[-1]) # Select the last matching column, by default.
            return idx

    def set_layer_join_field_default(self):
        if not hasattr(self, 'model'):
            return
        if layer := self.ui.qgsComboLayer.currentLayer():
            if idx := self.infer_join_field_idx_from_layer(layer=layer):
                self.ui.qgsComboLayerJoinField.setCurrentIndex(idx)

    def set_dataset_table(self):
        self.dataset = Dataset(db=self.database, code=self.get_selected_dataset_code(), lang=self.get_selected_language())
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
        string = '{abbrev} [{name}]'
        items = [string.format(abbrev=abbrev, name=name) for abbrev, name in
                 self.base.dataset.get_param_full_name(param=self.name)]
        self.ui.listItems.addItems(items)

    def get_listitem_text_abbrev(self, item: QtWidgets.QListWidgetItem):
        return item.text().split(' [')[0] # The string variable inside populate_list.

    def select_based_on_filterer(self):
        if self.name in self.base.filterer.row:
            for row in range(self.ui.listItems.count()):
                item = self.ui.listItems.item(row)
                item.setSelected(self.get_listitem_text_abbrev(item) in self.base.filterer.row[self.name])

    def get_line_search_text(self):
        return self.ui.lineSearch.text()

    def filter_list_items(self):
        search_text = self.get_line_search_text().lower()
        for row in range(self.ui.listItems.count()):
            item = self.ui.listItems.item(row)
            item_text = item.text().lower()
            item.setHidden(search_text not in item_text)

    def get_selected_items(self):
        return [self.get_listitem_text_abbrev(item) for item in self.ui.listItems.selectedItems()]

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
    # TODO: maybe add different behaviour for the GEO column later?
    def __init__(self, section_dialog: ParameterSectionDialog, name: str):
        self.section_dialog = section_dialog
        self.name = name


class CommonGeoSectionNames(Enum):
    """Enumerates the common fields which describe geographic areas."""
    # NOTE: Feel free to expand this enum
    GEO = 'geo'
    REP_MAR = 'rep_mar'
    METROREG = 'metroreg'


class FrequencyTypes(Enum):
    """Enumerates the frequency types associated with a dataset."""
    ANNUALLY = 'a'
    

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
        # NOTE: this would have been a great match case spot but idk if qgis users have python >= 3.10
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
            raise ValueError(f'No frequency column was found. Unknown {freq}.')
    
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
    def date_columns(self) -> Union[list[str], list]:
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
    return [combobox.itemText(idx) for idx in range(combobox.count())]


@dataclass(init=False)
class Exporter:
    
    def __init__(self, base: Dialog):
        self.base = base

    def add_table(self):
        table = self.base.converter.table
        table.setName(self.base.dataset.code)
        QgsProject.instance().addMapLayer(table)


@dataclass(init=False)
class JoinHandler:
    
    def __init__(self, base: Dialog):
        self.base = base

    @property
    def join_info(self):
        return self.get_join_info()

    def get_join_info(self):
        table = self.base.converter.table
        QgsProject.instance().addMapLayer(table)
        join_info = QgsVectorLayerJoinInfo()
        join_info.setJoinFieldName(self.base.ui.comboTableJoinField.currentText())
        join_info.setTargetFieldName(self.base.ui.qgsComboLayerJoinField.currentText())
        join_info.setJoinLayerId(table.id())
        join_info.setUsingMemoryCache(True)
        join_info.setJoinLayer(table)
        join_info.setPrefix(self.base.ui.linePrefix.text())
        return join_info

    def join_table_to_layer(self):
        self.base.ui.qgsComboLayer.currentLayer().addJoin(self.join_info)


@dataclass(init=False)
class QgsConverter:

    def __init__(self, base: Dialog):
        self.base = base

    @property
    def table(self):
        return self.from_dataframe(self.base.model.pandas._data)

    @staticmethod
    def dtype_mapper(series: pd.Series):
        dtype = series.dtype
        if pd.api.types.is_float_dtype(dtype):
            return QtCore.QVariant.Type.Double
        elif pd.api.types.is_integer_dtype(dtype):
            return QtCore.QVariant.Type.Int
        elif pd.api.types.is_datetime64_any_dtype(dtype):
            return QtCore.QVariant.Type.DateTime
        elif pd.api.types.is_bool_dtype(dtype):
            return QtCore.QVariant.Type.Bool
        else:
            return QtCore.QVariant.Type.String

    @staticmethod
    def to_dataframe(layer: QgsVectorLayer):
        # Source code: https://stackoverflow.com/a/76153082
        return (
            pd.DataFrame([feat.attributes() for feat in layer.getFeatures()],
                          columns=[field.name() for field in layer.fields()])
        )

    def from_dataframe(self, df: pd.DataFrame) -> QgsVectorLayer:
        """Method to convert a pandas dataframe to a qgis table layer."""
        temp = QgsVectorLayer('none', 'table', 'memory')
        temp_data = temp.dataProvider()
        temp.startEditing()
        attributes = []
        for head in df.columns:
            attributes.append(QgsField(head, self.dtype_mapper(series=df[head])))
        temp_data.addAttributes(attributes)
        temp.updateFields()
        rows = []
        for row in df.itertuples():
            f = QgsFeature()
            f.setAttributes([row[idx] for idx in range(1, len(row))])
            rows.append(f)
        temp_data.addFeatures(rows)
        temp.commitChanges()
        return temp
