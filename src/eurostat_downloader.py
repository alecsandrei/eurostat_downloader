from __future__ import annotations

import time
from typing import (
    Union,
    Iterable,
    Any,
)
from enum import Enum
from dataclasses import (
    dataclass,
    field
)
import itertools
from functools import partial

import numpy as np
import pandas as pd
from qgis.PyQt import (
    QtCore,
    QtWidgets,
    QtGui
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
from .utils import CheckableComboBox


class Dialog(QtWidgets.QDialog):

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
        self.dataset = None
        self.subset = None

        # Init table of contents
        QtCore.QTimer.singleShot(1, self.initialize_database)

        # Signals
        self.ui.qgsComboLayer.layerChanged.connect(self.set_layer_join_fields)
        self.ui.qgsComboLayer.layerChanged.connect(
            self.set_layer_join_field_default
        )
        self.ui.lineSearch.textChanged.connect(self.filter_toc)
        self.ui.listDatabase.itemPressed.connect(
            self.set_dataset_table
        )
        self.ui.tableDataset.horizontalHeader().sectionClicked.connect(
            self.open_section_ui
        )
        self.ui.buttonReset.clicked.connect(self.reset_dataset_table)
        self.ui.buttonAdd.clicked.connect(self.exporter.add_table)
        self.ui.buttonJoin.clicked.connect(
            self.join_handler.join_table_to_layer
        )
        for language_check in (
            self.ui.checkEnglish, self.ui.checkGerman, self.ui.checkFrench
        ):
            language_check.stateChanged.connect(self.update_language_check)
            language_check.stateChanged.connect(self.filter_toc)

    def set_layer_join_fields(self):
        layer = self.ui.qgsComboLayer.currentLayer()
        if not layer:
            return
        self.ui.qgsComboLayerJoinField.setLayer(layer=layer)

    def set_gui_state(self, state: bool):
        for obj in self.children():
            if isinstance(obj, QtWidgets.QWidget):
                obj.setEnabled(state)

    def initialize_database(self):
        self.ui.listDatabase.clear()
        initializer = DatabaseInitializer(self)
        dialog = LoadingDialog(self)
        loading_label = LoadingLabel(
            'initializing table of contents', self
        )
        initializer.started.connect(
            partial(self.set_gui_state, False)
        )
        initializer.started.connect(
            dialog.show
        )
        loading_label.update_label.connect(dialog.update_loading_label)
        initializer.started.connect(
            loading_label.start
        )
        initializer.finished.connect(
            partial(self.set_gui_state, True)
        )
        initializer.finished.connect(
            loading_label.requestInterruption
        )
        initializer.finished.connect(
            dialog.close
        )
        initializer.start()

    def filter_toc(self):
        self.ui.listDatabase.clear()
        self.subset = self.database.get_subset(
            self.ui.lineSearch.text()
        )
        titles = self.database.get_titles(subset=self.subset)
        codes = self.database.get_codes(subset=self.subset)
        items = '[' + codes + '] ' + titles
        self.ui.listDatabase.addItems(items)

    def get_selected_dataset_code(self):
        row = self.ui.listDatabase.currentRow()
        if self.subset is None:
            self.subset = self.database.toc
        return self.database.get_codes(subset=self.subset).iloc[row]

    def get_current_table_join_field(self):
        return self.ui.comboTableJoinField.currentText()

    def update_language_check(self):
        language_checks = [
            self.ui.checkEnglish, self.ui.checkFrench, self.ui.checkGerman
        ]
        sender = self.sender()
        assert isinstance(sender, QtWidgets.QCheckBox)
        if sender.isChecked():
            language_checks.remove(sender)
            for check in language_checks:
                check.setChecked(False)
        selected_language = self.get_selected_language()
        if self.dataset is not None:
            self.dataset.set_language(lang=selected_language)
        self.database.set_language(lang=selected_language)

    def get_selected_language(self):
        if self.ui.checkFrench.isChecked():
            return Language.FRENCH
        elif self.ui.checkGerman.isChecked():
            return Language.GERMAN
        return Language.ENGLISH

    def set_table_join_fields(self):
        self.ui.comboTableJoinField.clear()
        assert self.dataset is not None
        self.ui.comboTableJoinField.addItems(self.dataset.params)

    def set_table_join_field_default(self):
        items = get_combobox_items(self.ui.comboTableJoinField)
        for idx, item in enumerate(items):
            # Is this supposed to be this weird to iterate through an Enum?
            if item in CommonGeoSectionNames._value2member_map_:
                self.ui.comboTableJoinField.setCurrentIndex(idx)

    def infer_join_field_idx_from_layer(self, layer: QgsMapLayer):
        assert isinstance(layer, QgsVectorLayer)
        if layer.featureCount() > 100_000:
            # Don't infer join field if there are more than 100k features.
            return
        df = self.converter.to_dataframe(layer=layer)
        geo = self.ui.comboTableJoinField.currentText()
        unique_values = self.model.pandas._data[geo].unique()
        columns = df.columns[df.isin(unique_values).any()]
        if not columns.empty:
            idx = df.columns.to_list().index(columns[-1])
            return idx

    def set_layer_join_field_default(self):
        if not hasattr(self, 'model'):
            return
        if layer := self.ui.qgsComboLayer.currentLayer():
            if idx := self.infer_join_field_idx_from_layer(layer=layer):
                self.ui.qgsComboLayerJoinField.setCurrentIndex(idx)

    def set_dataset_table(self):
        self.dataset = Dataset(
            db=self.database,
            code=self.get_selected_dataset_code(),
            lang=self.get_selected_language()
        )
        initializer = DatasetInitializer(self)
        dialog = LoadingDialog(self)
        loading_label = LoadingLabel(
            f'initializing dataset "{self.dataset.code}"', self
        )
        initializer.started.connect(
            partial(self.set_gui_state, False)
        )
        initializer.started.connect(
            dialog.show
        )
        loading_label.update_label.connect(dialog.update_loading_label)
        initializer.started.connect(
            loading_label.start
        )
        initializer.finished.connect(
            partial(self.set_gui_state, True)
        )
        initializer.finished.connect(
            loading_label.requestInterruption
        )
        initializer.finished.connect(
            dialog.close
        )
        initializer.start()
        initializer.finished.connect(self.set_table_join_fields)
        initializer.finished.connect(self.set_table_join_field_default)
        initializer.finished.connect(self.set_layer_join_field_default)
        initializer.finished.connect(self.set_join_columns)

    def set_join_columns(self):
        checkable = CheckableComboBox()
        self.ui.verticalLayoutColumnsToJoin.replaceWidget(
            self.ui.comboBoxColumnsToJoin, checkable
        )
        self.ui.comboBoxColumnsToJoin.close()
        self.ui.comboBoxColumnsToJoin = checkable
        assert self.dataset is not None
        self.ui.comboBoxColumnsToJoin.addItems(
            self.dataset.params
        )
        self.ui.comboBoxColumnsToJoin.setCurrentIndex(-1)

    def update_model(self):
        assert self.dataset is not None
        self.model = DatasetModel(
            estat_dataset=self.dataset, filterer=self.filterer
        )
        self.ui.tableDataset.setModel(self.model.pandas)

    def open_section_ui(self, idx):
        assert self.dataset is not None
        section_name = self.dataset.df.columns[idx]
        if section_name in self.dataset.params:
            ParameterSectionDialog(base=self, name=section_name)
        elif section_name in self.dataset.date_columns:
            TimeSectionDialog(base=self, name=section_name)

    def reset_dataset_table(self):
        if self.dataset is not None:
            self.filterer.remove_row_filters()
            self.filterer.set_column_filters()
            self.update_model()


class DatabaseInitializer(QtCore.QThread):
    def __init__(self, base: Dialog):
        self.base = base
        super().__init__(self.base)

    def run(self):
        self.base.ui.listDatabase.clear()
        self.base.database.initialize_toc()
        titles = self.base.database.get_titles()
        codes = self.base.database.get_codes()
        items = '[' + codes + '] ' + titles
        self.base.ui.listDatabase.addItems(items)


class DatasetInitializer(QtCore.QThread):
    def __init__(self, base: Dialog):
        self.base = base
        super().__init__(self.base)

    def run(self):
        assert self.base.dataset is not None
        self.base.dataset.initialize_df()
        self.base.filterer = DataFilterer(dataset=self.base.dataset)
        self.base.update_model()


class LoadingLabel(QtCore.QThread):
    update_label = QtCore.pyqtSignal(str)

    def __init__(self, label: str, base=None):
        self.base = base
        super().__init__(base)
        self.label = label

    def spin(self):
        for char in itertools.cycle('🌏🌍🌎'):
            self.update_label.emit(f'{self.label}\n{char}  ')
            time.sleep(0.5)
            if self.isInterruptionRequested():
                break

    def run(self):
        self.spin()


class LoadingDialog(QtWidgets.QDialog):
    def __init__(self, base=None):
        self.base = base
        super().__init__(base)
        self.setWindowTitle(' ')
        layout = QtWidgets.QVBoxLayout(self)
        layout.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self.setLayout(layout)
        self.qlabel = QtWidgets.QLabel(self)
        self.qlabel.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self.qlabel.setFont(QtGui.QFont(self.qlabel.font().family(), 15))
        self.layout().addWidget(self.qlabel)

    def update_loading_label(self, text: str):
        self.qlabel.setText(text)


class ParameterSectionDialog(QtWidgets.QDialog):

    def __init__(self, base: Dialog, name: str):
        super().__init__()
        self.base = base
        self.name = name
        self.ui = UIParameterSectionDialog()
        self.ui.setupUi(self)
        self.filter_toc()
        self.select_based_on_filterer()
        self.section_type_handler()

        # Signals
        self.ui.lineSearch.textChanged.connect(self.filter_list_items)
        self.ui.buttonReset.clicked.connect(self.reset_selection)
        self.ui.listItems.itemSelectionChanged.connect(self.filter_table)

        self.exec_()

    def reset_selection(self):
        self.ui.listItems.clearSelection()

    def filter_toc(self):
        assert self.base.dataset is not None
        if self.base.dataset.lang is not None:
            names = (
                self.base.dataset.params_info
                [self.base.dataset.lang]
                [self.name]
            )
            assert names is not None
            items = [f'{abbrev} [{name}]' for abbrev, name in names]
        else:
            items = self.base.dataset.df[self.name].unique()
        self.ui.listItems.addItems(items)

    def get_listitem_text_abbrev(self, item: QtWidgets.QListWidgetItem):
        # The string variable inside filter_toc.
        return item.text().split(' [')[0]

    def select_based_on_filterer(self):
        if self.name in self.base.filterer.row:
            for row in range(self.ui.listItems.count()):
                item = self.ui.listItems.item(row)
                if item is not None:
                    item.setSelected(
                        self.get_listitem_text_abbrev(item)
                        in self.base.filterer.row[self.name]
                    )

    def get_line_search_text(self):
        return self.ui.lineSearch.text()

    def filter_list_items(self):
        search_text = self.get_line_search_text().lower()
        for row in range(self.ui.listItems.count()):
            item = self.ui.listItems.item(row)
            if item is not None:
                item_text = item.text().lower()
                item.setHidden(search_text not in item_text)

    def get_selected_items(self):
        return (
            [self.get_listitem_text_abbrev(item)
             for item in self.ui.listItems.selectedItems()]
        )

    def section_type_handler(self):
        if (
            self.name
            == (geo_field := self.base.get_current_table_join_field())
        ):
            GeoParameterSectionDialog(section_dialog=self, name=geo_field)

    def filter_table(self):
        if self.name in self.base.filterer.row:
            self.base.filterer.remove_row_filters(filters=self.name)
        if self.get_selected_items():
            self.base.filterer.add_row_filters(
                filters={self.name: self.get_selected_items()}
            )
        self.base.update_model()


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
    SEMESTERLY = 's'
    QUARTERLY = 'q'
    MONTHLY = 'm'
    DAILY = 'd'


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

    def get_frequency_types(self):
        assert self.base.dataset is not None
        freq = self.base.dataset.frequency.lower()
        if freq == FrequencyTypes.ANNUALLY.value:
            return ['Year']
        elif freq == FrequencyTypes.SEMESTERLY.value:
            return ['Year', 'Semester']
        elif freq == FrequencyTypes.QUARTERLY.value:
            return ['Year', 'Quarter']
        elif freq == FrequencyTypes.MONTHLY.value:
            return ['Year', 'Month']
        elif freq == FrequencyTypes.DAILY.value:
            return ['Year', 'Month', 'Day']
        else:
            raise ValueError(f'No frequency column was found. Unknown {freq}.')

    def add_labels_to_frames(self, frequency: str):
        frequency = frequency.capitalize()
        label_object_name = ''.join(['label', frequency])
        self.ui.add_label_to_frames(
            object_name=label_object_name, text=frequency
        )

    def add_combobox_to_frames(self, frequency: str):
        frequency = frequency.capitalize()
        combo_object_name = ''.join(['combo', frequency])
        self.ui.add_combobox_to_frames(object_name=combo_object_name)

    def add_widgets_to_frames(self):
        for frequency in self.get_frequency_types():
            self.add_labels_to_frames(frequency)
            self.add_combobox_to_frames(frequency)

    def add_items_to_start_combobox(self):
        for idx, frequency in enumerate(self.get_frequency_types()):
            widget = self.ui.frameStart.findChild(
                QtWidgets.QComboBox, ''.join(['combo', frequency])
            )
            assert self.base.dataset is not None
            widget.addItems(self.base.dataset.date_columns
                            .str.split('-')
                            .str.get(idx)
                            .unique())

    def add_items_to_end_combobox(self):
        for idx, frequency in enumerate(self.get_frequency_types()):
            widget = self.ui.frameEnd.findChild(
                QtWidgets.QComboBox, ''.join(['combo', frequency])
            )
            assert self.base.dataset is not None
            items = (self.base.dataset
                     .date_columns
                     .str.split('-')
                     .str.get(idx)
                     .unique())
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
        for frequency in self.get_frequency_types():
            widget = self.ui.frameStart.findChild(
                QtWidgets.QComboBox, ''.join(['combo', frequency])
            )
            times.append(widget.currentText())
        return '-'.join(times)

    def get_end_time_combobox(self):
        times = []
        for frequency in self.get_frequency_types():
            widget = self.ui.frameEnd.findChild(
                QtWidgets.QComboBox, ''.join(['combo', frequency])
            )
            times.append(widget.currentText())
        return '-'.join(times)

    def add_time_filters(self):
        assert self.base.dataset is not None
        cols = self.base.dataset.date_columns.to_list()
        try:
            start = cols.index(self.get_start_time_combobox())
        except ValueError:
            start = 0
        try:
            end = cols.index(self.get_end_time_combobox())
        except ValueError:
            end = len(cols) - 1
        cols_filtered = cols[start:end+1]
        cols = self.base.dataset.params + cols_filtered
        self.base.filterer.set_column_filters(filters=cols)
        self.base.update_model()

    def set_default_start_combobox(self):
        for idx, frequency in enumerate(self.get_frequency_types()):
            widget = self.ui.frameStart.findChild(
                QtWidgets.QComboBox, ''.join(['combo', frequency])
            )
            assert self.base.dataset is not None
            items = self.base.dataset.date_columns.str.split('-').str.get(idx)
            items_first = items[0]
            items_unique = items.unique()
            default_index = items_unique.to_list().index(items_first)
            widget.setCurrentIndex(default_index)

    def set_default_end_combobox(self):
        for idx, frequency in enumerate(self.get_frequency_types()):
            widget = self.ui.frameEnd.findChild(
                QtWidgets.QComboBox, ''.join(['combo', frequency])
            )
            assert self.base.dataset is not None
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
        for idx, frequency in enumerate(self.get_frequency_types()):
            widget = self.ui.frameStart.findChild(
                QtWidgets.QComboBox, ''.join(['combo', frequency])
            )
            items = get_combobox_items(combobox=widget)
            if items:
                idx = items.index(
                    self.base.filterer.date_columns[0].split('-')[idx]
                )
                widget.setCurrentIndex(idx)

    def restore_end_combobox(self):
        for idx, frequency in enumerate(self.get_frequency_types()):
            widget = self.ui.frameEnd.findChild(
                QtWidgets.QComboBox, ''.join(['combo', frequency])
            )
            items = get_combobox_items(combobox=widget)
            if items:
                idx = items.index(
                    self.base.filterer.date_columns[-1].split('-')[idx]
                )
                widget.setCurrentIndex(idx)

    def restore(self):
        self.restore_start_combobox()
        self.restore_end_combobox()


@dataclass
class DataFilterer:
    dataset: Dataset
    row: dict[str, list[Any]] = field(init=False, default_factory=dict)
    column: list[str] = field(init=False, default_factory=list)

    def __post_init__(self):
        self.column = self.dataset.df.columns.to_list()

    @property
    def df(self):
        return self.dataset.df

    @property
    def date_columns(self) -> Union[list[str], list]:
        return np.setdiff1d(self.column, self.dataset.params).tolist()

    def apply_filters(self):
        ind = [True] * len(self.df)
        for col, vals in self.row.items():
            if not vals:
                continue
            # TODO: Fix the following line of code. A Pandas FutureWarning.
            ind = ind & (self.df[col].isin(vals))
        return self.df.loc[ind, self.column]

    def add_row_filters(self, filters: dict[str, Iterable[Any]]):
        # This is only for the row axis
        for col, values in filters.items():
            for value in values:
                self.row.setdefault(col, []).append(value)

    def set_column_filters(
        self,
        filters: Union[None, str, Iterable[str]] = None
    ):
        if filters is None:
            filters = self.dataset.df.columns.to_list()
        elif isinstance(filters, str):
            filters = [filters]
        self.column = list(filters)

    def remove_row_filters(
        self,
        filters: Union[None, str, dict[str, Iterable], Iterable[str]] = None
    ):
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
        if (
            orientation == QtCore.Qt.Orientation.Horizontal
            and role == QtCore.Qt.ItemDataRole.DisplayRole
        ):
            return self._data.columns[col]
        return None


def get_combobox_items(combobox: QtWidgets.QComboBox) -> list[str]:
    return [combobox.itemText(idx) for idx in range(combobox.count())]


class Exporter:
    base: Dialog

    def __init__(self, base: Dialog):
        self.base = base

    def add_table(self):
        table = self.base.converter.table
        table.setName(self.base.dataset.code)
        QgsProject.instance().addMapLayer(table)  # type: ignore


class JoinHandler:
    base: Dialog

    def __init__(self, base: Dialog):
        self.base = base

    @property
    def join_info(self):
        return self.get_join_info()

    def get_join_info(self):
        table = self.base.converter.table
        QgsProject.instance().addMapLayer(table)  # type: ignore
        join_info = QgsVectorLayerJoinInfo()
        join_info.setJoinFieldName(
            self.base.ui.comboTableJoinField.currentText()
        )
        join_info.setTargetFieldName(
            self.base.ui.qgsComboLayerJoinField.currentText()
        )
        join_info.setJoinFieldNamesSubset(
            itertools.chain(
                self.base.ui.comboBoxColumnsToJoin.currentData(),
                self.base.dataset.date_columns
            )
        )
        join_info.setJoinLayerId(table.id())
        join_info.setUsingMemoryCache(True)
        join_info.setJoinLayer(table)
        join_info.setPrefix(self.base.ui.linePrefix.text())
        return join_info

    def join_table_to_layer(self):
        self.base.ui.qgsComboLayer.currentLayer().addJoin(self.join_info)


class QgsConverter:
    base: Dialog

    def __init__(self, base: Dialog):
        self.base = base

    @property
    def table(self):
        return self.from_dataframe(self.base.model.pandas._data)

    @staticmethod
    def dtype_mapper(series: pd.Series):
        dtype = series.dtype
        if pd.api.types.is_integer_dtype(dtype):
            return QtCore.QVariant.Type.Int
        elif pd.api.types.is_float_dtype(dtype):
            return QtCore.QVariant.Type.Double
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
            pd.DataFrame(
                [
                    feat.attributes()
                    for feat in layer.getFeatures()  # type: ignore
                ],
                columns=[field.name() for field in layer.fields()]
            )
        )

    def from_dataframe(self, df: pd.DataFrame) -> QgsVectorLayer:
        """Method to convert a pandas dataframe to a qgis table layer."""
        temp = QgsVectorLayer('none', self.base.dataset.code, 'memory')
        temp_data = temp.dataProvider()
        temp.startEditing()
        attributes = []
        for head in df.columns:
            attributes.append(
                QgsField(head, self.dtype_mapper(series=df[head]))
            )
        temp_data.addAttributes(attributes)  # type: ignore
        temp.updateFields()
        rows = []
        for row in df.itertuples():
            f = QgsFeature()
            f.setAttributes([row[idx] for idx in range(1, len(row))])
            rows.append(f)
        temp_data.addFeatures(rows)  # type: ignore
        temp.commitChanges()
        return temp
