from __future__ import annotations

import itertools
import os.path
import time
import traceback
import typing as t
from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import astuple, dataclass, field, fields
from enum import Enum, auto
from functools import partial
from typing import (
    Callable,
    Literal,
    cast,
)

import processing
from qgis.core import (
    QgsFeature,
    QgsField,
    QgsJsonUtils,
    QgsMapLayer,
    QgsNetworkAccessManager,
    QgsProject,
    QgsVectorLayer,
    QgsVectorLayerJoinInfo,
)
from qgis.gui import QgisInterface
from qgis.PyQt import QtCore, QtGui, QtNetwork, QtWidgets
from qgis.PyQt.QtCore import QCoreApplication, Qt
from qgis.PyQt.QtWidgets import QAction, QDialog

from eurostat_downloader import resources  # noqa: F401
from eurostat_downloader.src import DEBUG
from eurostat_downloader.src.data import (
    GISCO,
    Database,
    Dataset,
    DatasetCell,
    DatasetPayload,
    TocRow,
    Unit,
    Units,
)
from eurostat_downloader.src.enums import (
    Agency,
    ConnectionStatus,
    FrequencyType,
    GeoSectionName,
    Language,
)
from eurostat_downloader.src.settings import GLOBAL_SETTINGS
from eurostat_downloader.src.ui.eurostat_downloader_dialog import Ui_EurostatDownloaderDialog
from eurostat_downloader.src.ui.gisco_dataset_information import Ui_GISCODatasetInformation
from eurostat_downloader.src.ui.gisco_join_report import Ui_GISCOJoinReport
from eurostat_downloader.src.ui.section_dialog_params import Ui_ParametersDialog
from eurostat_downloader.src.ui.section_dialog_time import Ui_TimePeriodDialog
from eurostat_downloader.src.ui.settings_dialog import Ui_SettingsDialog
from eurostat_downloader.src.utils import (
    CheckableComboBox,
    QComboboxCompleter,
    color_row,
    get_table_item,
    layer_from_features,
)


class LayerPayload(t.TypedDict):
    columns: list[str]
    data: list[list[object]]


class Tabs(Enum):
    LAYER = auto()
    GISCO = auto()


class EurostatDownloader:
    """QGIS Plugin Implementation."""

    def __init__(self, iface: QgisInterface) -> None:
        """Constructor.

        :param iface: An interface instance that will be passed to this class
            which provides the hook by which you can manipulate the QGIS
            application at run time.
        :type iface: QgsInterface
        """
        # Save reference to the QGIS interface
        self.iface = iface
        # initialize plugin directory
        self.plugin_dir = os.path.dirname(__file__)
        # initialize locale
        locale = (QtCore.QSettings().value('locale/userLocale') or 'en')[0:2]
        locale_path = os.path.join(
            self.plugin_dir, 'i18n', 'EurostatDownloader_{}.qm'.format(locale)
        )

        if os.path.exists(locale_path):
            self.translator = QtCore.QTranslator()
            self.translator.load(locale_path)
            QCoreApplication.installTranslator(self.translator)

        # Declare instance attributes
        self.actions: list[QAction] = []
        self.menu = self.tr('&Eurostat Downloader')

        # Check if plugin was started the first time in current QGIS session
        # Must be set in initGui() to survive plugin reloads
        self.first_start: bool | None = None

    # noinspection PyMethodMayBeStatic
    def tr(self, message: str) -> str:
        """Get the translation for a string using Qt translation API.

        We implement this ourselves since we do not inherit QObject.

        :param message: String for translation.
        :type message: str, QString

        :returns: Translated version of message.
        :rtype: QString
        """
        # noinspection PyTypeChecker,PyArgumentList,PyCallByClass
        return cast(str, QCoreApplication.translate('EurostatDownloader', message))

    def add_action(  # type: ignore[explicit-any]  # Callable[..., X] uses `...` which mypy treats as Any; callbacks here genuinely accept arbitrary signatures from Qt signals
        self,
        icon_path: str,
        text: str,
        callback: Callable[..., object],
        enabled_flag: bool = True,
        add_to_menu: bool = True,
        add_to_toolbar: bool = True,
        status_tip: str | None = None,
        whats_this: str | None = None,
        parent: QtWidgets.QWidget | None = None,
    ) -> QAction:
        """Add a toolbar icon to the toolbar.

        :param icon_path: Path to the icon for this action. Can be a resource
            path (e.g. ':/plugins/foo/bar.png') or a normal file system path.
        :type icon_path: str

        :param text: Text that should be shown in menu items for this action.
        :type text: str

        :param callback: Function to be called when the action is triggered.
        :type callback: function

        :param enabled_flag: A flag indicating if the action should be enabled
            by default. Defaults to True.
        :type enabled_flag: bool

        :param add_to_menu: Flag indicating whether the action should also
            be added to the menu. Defaults to True.
        :type add_to_menu: bool

        :param add_to_toolbar: Flag indicating whether the action should also
            be added to the toolbar. Defaults to True.
        :type add_to_toolbar: bool

        :param status_tip: Optional text to show in a popup when mouse pointer
            hovers over the action.
        :type status_tip: str

        :param parent: Parent widget for the new action. Defaults None.
        :type parent: QWidget

        :param whats_this: Optional text to show in the status bar when the
            mouse pointer hovers over the action.

        :returns: The action that was created. Note that the action is also
            added to self.actions list.
        :rtype: QAction
        """

        icon = QtGui.QIcon(icon_path)
        action = QAction(icon, text, parent)
        action.triggered.connect(callback)
        action.setEnabled(enabled_flag)

        if status_tip is not None:
            action.setStatusTip(status_tip)

        if whats_this is not None:
            action.setWhatsThis(whats_this)

        if add_to_toolbar:
            # Adds plugin icon to Plugins toolbar
            self.iface.addToolBarIcon(action)

        if add_to_menu:
            self.iface.addPluginToMenu(self.menu, action)

        self.actions.append(action)

        return action

    def initGui(self) -> None:
        """Create the menu entries and toolbar icons inside the QGIS GUI."""

        icon_path = ':/plugins/eurostat_downloader/assets/icon.png'
        self.add_action(
            icon_path,
            text=self.tr('Get Eurostat data'),
            callback=self.run,
            parent=self.iface.mainWindow(),
        )

        # will be set False in run()
        self.first_start = True

    def unload(self) -> None:
        """Removes the plugin menu item and icon from QGIS GUI."""
        for action in self.actions:
            self.iface.removePluginMenu(self.tr('&Eurostat Downloader'), action)
            self.iface.removeToolBarIcon(action)

    def run(self) -> None:
        """Run method that performs all the real work"""

        # Create the dialog with elements (after translation) and keep reference
        # Only create GUI ONCE in callback, so that it will only load when the plugin is started
        if self.first_start:
            self.first_start = False
            self.dlg = Dialog(self)

        # show the dialog
        self.dlg.show()
        # Run the dialog event loop
        result = self.dlg.exec()
        # See if OK was pressed
        if result:
            # Do something useful here - delete the line containing pass and
            # substitute with your code.
            pass


class Dialog(QtWidgets.QDialog):  # type: ignore[misc]  # QDialog is Any without stubs
    def __init__(self, eurostat_downloader: EurostatDownloader) -> None:
        super().__init__()

        # Init GUI
        self.eurostat_downloader = eurostat_downloader
        self.ui = Ui_EurostatDownloaderDialog()
        self.ui.setupUi(self)  # type: ignore[no-untyped-call]  # generated UI module not type-checked
        self.set_layer_join_fields()

        # Instantiate objects
        self.database = Database()
        self.gisco_handler = GISCOHandler(self)
        self.join_handler = JoinHandler(base=self)
        self.exporter = Exporter(base=self)
        self.converter = QgsConverter(base=self)
        self.dataset: Dataset | None = None
        self.subset: list[TocRow] | None = None
        self.filterer: DataFilterer | None = None

        # Search debounce timer
        self.search_timer = QtCore.QTimer()
        self.search_timer.setSingleShot(True)
        self.search_timer.timeout.connect(self.filter_toc)

        # Signals
        self.ui.pushButtonInitializeTOC.clicked.connect(
            self.initialize_database
        )
        self.ui.qgsComboLayer.layerChanged.connect(self.set_layer_join_fields)
        self.ui.qgsComboLayer.layerChanged.connect(
            self.set_layer_join_field_default
        )
        self.ui.lineSearch.textChanged.connect(self.on_search_text_changed)
        self.ui.treeDatabase.itemClicked.connect(self.set_dataset_table)
        self.ui.tableDataset.horizontalHeader().sectionClicked.connect(
            self.open_section_ui
        )
        self.ui.toolButtonSettings.clicked.connect(self.open_settings_ui)
        self.ui.buttonReset.clicked.connect(self.reset_dataset_table)
        self.ui.buttonAdd.clicked.connect(self.exporter.add_table)
        self.ui.buttonJoin.clicked.connect(
            self.join_handler.join_table_to_layer
        )
        for language_check in (
            self.ui.checkEnglish,
            self.ui.checkGerman,
            self.ui.checkFrench,
        ):
            language_check.stateChanged.connect(self.update_language_check)
            language_check.stateChanged.connect(self.filter_toc)
        self.ui.tabWidget.currentChanged.connect(self.handle_tab_change)

    def handle_tab_change(self, index: int) -> None:
        match Tabs(index + 1):
            case Tabs.LAYER:
                ...
            case Tabs.GISCO:
                self.gisco_handler.add_themes()

    def set_agency_status_tooltip(self) -> None:
        tooltip = ['Agency server accessibility']
        for agency, status in self.database._agency_status.items():
            mark = '[OK]' if status == ConnectionStatus.AVAILABLE else '[X]'
            tooltip.append(f'{agency.name} {mark}')
        self.ui.labelAgencyStatus.setToolTip('\n'.join(tooltip))

    def open_settings_ui(self) -> None:
        SettingsDialog(self)

    def set_layer_join_fields(self) -> None:
        layer = self.ui.qgsComboLayer.currentLayer()
        if not layer:
            return
        self.ui.qgsComboLayerJoinField.setLayer(layer=layer)

    def set_gui_state(self, state: bool) -> None:
        for obj in self.children():
            if isinstance(obj, QtWidgets.QWidget):
                obj.setEnabled(state)

    def initialize_database(self) -> None:
        self.ui.treeDatabase.clear()
        # Temporarily disconnect the textChanged signal to prevent double population
        self.ui.lineSearch.textChanged.disconnect(self.on_search_text_changed)

        initializer = DatabaseInitializer(self)
        dialog = LoadingDialog(self)
        loading_label = LoadingLabel('initializing table of contents', self)
        initializer.started.connect(partial(self.set_gui_state, False))
        initializer.started.connect(dialog.show)
        loading_label.update_label.connect(dialog.update_loading_label)
        initializer.started.connect(loading_label.start)
        initializer.finished.connect(partial(self.set_gui_state, True))
        initializer.finished.connect(loading_label.requestInterruption)
        initializer.finished.connect(dialog.close)
        initializer.error_ocurred.connect(self.handle_error_ocurred)
        initializer.finished.connect(self.set_agency_status_tooltip)

        # Reconnect the signal after initialization
        initializer.finished.connect(
            lambda: self.ui.lineSearch.textChanged.connect(
                self.on_search_text_changed
            )
        )

        initializer.start()

    def populate_tree(
        self,
        items: Sequence[TocRow],
        preserve_expansion: bool = False,
    ) -> None:
        """Populate QTreeWidget with hierarchical data.

        Args:
            items: List of TOC items to populate
            preserve_expansion: If True, preserve the current expansion state
        """
        if DEBUG:
            print(f'🌳 populate_tree() called with {len(items)} items')
            traceback.print_stack(limit=5)

        # Save expansion state if requested
        expanded_codes: set[str] = set()
        if preserve_expansion:
            expanded_codes = self._get_expanded_item_codes()

        self.ui.treeDatabase.clear()

        # Group items by agency
        agency_items: dict[str, list[TocRow]] = defaultdict(list)
        for item in items:
            agency = item.get('agency', 'EUROSTAT')
            agency_items[agency].append(item)

        # Build tree for each agency
        for agency, agency_item_list in sorted(agency_items.items()):
            # Create agency root node
            agency_root = QtWidgets.QTreeWidgetItem([agency, ''])
            font = agency_root.font(0)
            font.setBold(True)
            font.setPointSize(font.pointSize() + 1)
            agency_root.setFont(0, font)
            agency_root.setFlags(QtCore.Qt.ItemFlag.ItemIsEnabled)
            self.ui.treeDatabase.addTopLevelItem(agency_root)

            # Stack to keep track of the last parent at each level
            parent_stack: list[QtWidgets.QTreeWidgetItem] = [agency_root]

            for item in agency_item_list:
                level = (
                    item.get('level', 0) + 1
                )  # +1 because agency is the new root
                title = item['title']
                code = item['code']
                item_type = item.get('type', '')

                # Create tree item with title and code
                tree_item = QtWidgets.QTreeWidgetItem([title, code])

                # Store the full item data
                tree_item.setData(0, QtCore.Qt.ItemDataRole.UserRole, item)

                # Only datasets (tables) are selectable, folders are just navigation
                if item_type in ['table', 'dataset']:
                    tree_item.setFlags(
                        tree_item.flags() | QtCore.Qt.ItemFlag.ItemIsSelectable
                    )
                else:
                    # Folders are not selectable but expandable
                    tree_item.setFlags(QtCore.Qt.ItemFlag.ItemIsEnabled)
                    # Make folders bold
                    font = tree_item.font(0)
                    font.setBold(True)
                    tree_item.setFont(0, font)

                # Adjust parent_stack to current level
                while len(parent_stack) > level:
                    parent_stack.pop()

                # Add to parent
                if parent_stack:
                    parent_stack[-1].addChild(tree_item)
                else:
                    agency_root.addChild(tree_item)

                # Add current item to stack
                parent_stack.append(tree_item)

        # Set better column proportions - use a helper method
        self._fix_column_widths()

        # Restore expansion state or collapse all
        if preserve_expansion and expanded_codes:
            self._restore_expanded_items(expanded_codes)
        else:
            # Collapse all top-level items to start
            self.ui.treeDatabase.collapseAll()
        
        # Fix column widths again after expand/collapse with a small delay
        QtCore.QTimer.singleShot(100, self._fix_column_widths)

    def _fix_column_widths(self) -> None:
        """Ensure dataset column is properly sized.
        
        This method can be called multiple times to ensure column widths
        are correct even after the widget has fully rendered.
        """
        # Use viewport width (actual displayable area) and ensure minimum widths
        viewport_width = self.ui.treeDatabase.viewport().width()
        # Fallback to widget width if viewport not ready
        if viewport_width < 100:
            viewport_width = self.ui.treeDatabase.width()

        # Give Dataset column 70% of width, Code column 30%
        # But ensure Dataset column is at least 350px
        dataset_width = max(int(viewport_width * 0.7), 350)
        code_width = max(int(viewport_width * 0.3), 150)

        self.ui.treeDatabase.setColumnWidth(0, dataset_width)
        self.ui.treeDatabase.setColumnWidth(1, code_width)

    def _get_expanded_item_codes(self) -> set[str]:
        """Get codes of all currently expanded items (including agency roots)."""
        expanded: set[str] = set()

        def check_item(item: QtWidgets.QTreeWidgetItem) -> None:
            if item.isExpanded():
                item_data = item.data(0, QtCore.Qt.ItemDataRole.UserRole)
                if item_data and 'code' in item_data:
                    # Regular item with code
                    expanded.add(item_data['code'])
                else:
                    # Agency root (no UserRole data) - use the text
                    expanded.add(f'__AGENCY__{item.text(0)}')

            # Recursively check children
            for i in range(item.childCount()):
                check_item(item.child(i))

        # Check all top-level items
        for i in range(self.ui.treeDatabase.topLevelItemCount()):
            check_item(self.ui.treeDatabase.topLevelItem(i))

        return expanded

    def _restore_expanded_items(self, expanded_codes: set[str]) -> None:
        """Restore expansion state for items with given codes."""

        def restore_item(item: QtWidgets.QTreeWidgetItem) -> None:
            item_data = item.data(0, QtCore.Qt.ItemDataRole.UserRole)
            if item_data and 'code' in item_data:
                # Regular item with code
                if item_data['code'] in expanded_codes:
                    item.setExpanded(True)
            else:
                # Agency root - check using text
                if f'__AGENCY__{item.text(0)}' in expanded_codes:
                    item.setExpanded(True)

            # Recursively restore children
            for i in range(item.childCount()):
                restore_item(item.child(i))

        # Restore all top-level items
        for i in range(self.ui.treeDatabase.topLevelItemCount()):
            restore_item(self.ui.treeDatabase.topLevelItem(i))

    def on_search_text_changed(self) -> None:
        """Debounce search input - wait 300ms after user stops typing."""
        self.search_timer.stop()
        self.search_timer.start(300)  # milliseconds

    def filter_toc(self) -> None:
        if not self.database.toc:  # Check if list is empty
            return None

        search_text = self.ui.lineSearch.text().lower()

        if not search_text:
            # No filter: show full hierarchy, preserve expansion (for language changes)
            self.populate_tree(self.database.toc, preserve_expansion=True)
            self.subset = None
        else:
            # Filter: show items matching search but preserve tree structure
            self.subset = self.database.get_subset(search_text)

            if not self.subset:
                self.ui.treeDatabase.clear()
                return

            # Build a set of matching codes - but ONLY for actual datasets, not folders
            matching_codes = {
                item['code']
                for item in self.subset
                if item.get('type', '') in ['table', 'dataset']
            }

            if not matching_codes:
                # No actual datasets match, only folders
                self.ui.treeDatabase.clear()
                return

            # Single pass: Add items and their parents only when we encounter a dataset match
            filtered_items: list[TocRow] = []
            parent_stack: list[TocRow] = []

            for item in self.database.toc:
                code = item['code']
                level = item.get('level', 0)
                item_type = item.get('type', '')

                # Adjust parent stack to current level
                while len(parent_stack) > level:
                    parent_stack.pop()

                # Only consider datasets as matches, not folders
                is_match = code in matching_codes and item_type in [
                    'table',
                    'dataset',
                ]

                if is_match:
                    # Add all parents from stack that aren't already in filtered_items
                    for parent in parent_stack:
                        if parent not in filtered_items:
                            filtered_items.append(parent)

                    # Add this matching dataset
                    filtered_items.append(item)

                # Always track in parent stack for hierarchy
                parent_stack.append(item)

            # Now populate tree with filtered items (in hierarchical order)
            self.populate_tree(filtered_items)

            # Expand all items so search results are visible
            self.ui.treeDatabase.expandAll()

            # Set column widths after filtering and expanding
            self._fix_column_widths()
            # Fix again with delay to ensure it's applied after full render
            QtCore.QTimer.singleShot(100, self._fix_column_widths)

    def get_selected_dataset_code(self) -> str | None:
        current_item = self.ui.treeDatabase.currentItem()
        if current_item is None:
            return None

        # Get the stored item data
        item_data = current_item.data(0, QtCore.Qt.ItemDataRole.UserRole)
        if item_data:
            return cast(str | None, item_data.get('code'))

        # Fallback: parse from the displayed code column
        return cast(str, current_item.text(1))

    def get_current_table_join_field(self) -> str:
        return cast(str, self.ui.comboTableJoinField.currentText())

    def update_language_check(self) -> None:
        language_checks = [
            self.ui.checkEnglish,
            self.ui.checkFrench,
            self.ui.checkGerman,
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

    def get_selected_language(self) -> Language:
        if self.ui.checkFrench.isChecked():
            return Language.FRENCH
        elif self.ui.checkGerman.isChecked():
            return Language.GERMAN
        return Language.ENGLISH

    def set_table_join_fields(self) -> None:
        self.ui.comboTableJoinField.clear()
        assert self.dataset is not None
        self.ui.comboTableJoinField.addItems(self.dataset.params)

    def set_table_join_field_default(self) -> None:
        items = get_combobox_items(self.ui.comboTableJoinField)
        for idx, item in enumerate(items):
            # Is this supposed to be this weird to iterate through an Enum?
            if item in GeoSectionName._value2member_map_:
                self.ui.comboTableJoinField.setCurrentIndex(idx)

    def infer_join_field_idx_from_layer(
        self, layer: QgsMapLayer
    ) -> int | None:
        assert isinstance(layer, QgsVectorLayer)
        if layer.featureCount() > 100_000:
            # Don't infer join field if there are more than 100k features.
            # NOTE: This is arbitrary, can be changed in the future.
            return None
        layer_data = self.converter.to_data_dict(layer=layer)
        geo = self.ui.comboTableJoinField.currentText()
        # Get unique values from the geo column
        model_data = self.model.table_model
        if geo in model_data._columns:
            geo_idx = model_data._columns.index(geo)
            unique_values = set(row[geo_idx] for row in model_data._data)
        else:
            return None

        # Find which column in layer contains these values
        for col_idx, col_name in enumerate(layer_data['columns']):
            col_values = set(row[col_idx] for row in layer_data['data'])
            if unique_values & col_values:  # If there's any overlap
                return col_idx
        return None

    def set_layer_join_field_default(self) -> None:
        if not hasattr(self, 'model'):
            return
        if layer := self.ui.qgsComboLayer.currentLayer():
            if idx := self.infer_join_field_idx_from_layer(layer=layer):
                self.ui.qgsComboLayerJoinField.setCurrentIndex(idx)

    def set_dataset_table(self) -> None:
        """Initialize dataset table when a dataset (not folder) is clicked."""
        current_item = self.ui.treeDatabase.currentItem()
        if current_item is None:
            return

        # Get the stored item data to check type
        item_data = current_item.data(0, QtCore.Qt.ItemDataRole.UserRole)
        if not item_data:
            # This is likely an agency root node, ignore
            return

        item_type = item_data.get('type', '')
        # Only initialize datasets, not folders
        if item_type not in ['table', 'dataset']:
            return

        code = self.get_selected_dataset_code()
        assert code is not None
        self.dataset = Dataset(
            db=self.database,
            code=code,
            lang=self.get_selected_language(),
        )
        initializer = DatasetInitializer(self)
        dialog = LoadingDialog(self)
        loading_label = LoadingLabel(
            f'initializing dataset "{self.dataset.code}"', self
        )
        initializer.started.connect(partial(self.set_gui_state, False))
        initializer.started.connect(dialog.show)
        loading_label.update_label.connect(dialog.update_loading_label)
        initializer.started.connect(loading_label.start)
        initializer.finished.connect(partial(self.set_gui_state, True))
        initializer.finished.connect(loading_label.requestInterruption)
        initializer.finished.connect(dialog.close)
        initializer.finished.connect(self.set_table_join_fields)
        initializer.finished.connect(self.set_table_join_field_default)
        initializer.finished.connect(self.set_layer_join_field_default)
        initializer.finished.connect(self.set_join_columns)
        initializer.finished.connect(self.gisco_handler.clear)
        initializer.error_ocurred.connect(self.handle_error_ocurred)
        initializer.start()

    def set_join_columns(self) -> None:
        checkable = CheckableComboBox()
        self.ui.verticalLayoutColumnsToJoin.replaceWidget(
            self.ui.comboBoxColumnsToJoin, checkable
        )
        self.ui.comboBoxColumnsToJoin.close()
        self.ui.comboBoxColumnsToJoin = checkable
        assert self.dataset is not None
        self.ui.comboBoxColumnsToJoin.addItems(self.dataset.params)
        self.ui.comboBoxColumnsToJoin.setCurrentIndex(-1)

    def update_model(self) -> None:
        assert self.dataset is not None
        assert self.filterer is not None
        self.model = DatasetModel(
            estat_dataset=self.dataset, filterer=self.filterer
        )
        self.ui.tableDataset.setModel(self.model.table_model)

    def open_section_ui(self, idx: int) -> None:
        assert self.dataset is not None
        assert self.dataset.data is not None
        section_name = self.dataset.data['columns'][idx]
        if section_name in self.dataset.params:
            ParameterSectionDialog(base=self, name=section_name)
        elif section_name in self.dataset.date_columns:
            TimeSectionDialog(base=self, name=section_name)

    def reset_dataset_table(self) -> None:
        # In case no table was filled and the user presses
        # the "Reset table" button
        if self.filterer is None:
            return None

        if self.dataset is not None:
            self.filterer.remove_row_filters()
            self.filterer.set_column_filters()
            self.update_model()

    def handle_error_ocurred(
        self, exception: Exception, action: Literal['raise', 'print'] = 'raise'
    ) -> None:
        # First 'if' is for debugging reasons.
        if action == 'print':
            print(exception)
        elif action == 'raise':
            raise exception


class GISCOUnitDownloader(QtCore.QObject):  # type: ignore[misc]  # QObject is Any without stubs
    finished = QtCore.pyqtSignal()
    unit_finished = QtCore.pyqtSignal(str, str, str)

    def __init__(
        self,
        handler: GISCOHandler,
        units: Units,
        parent: QtCore.QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self.handler = handler
        self.gisco = self.handler.get_theme()
        self.nam = QgsNetworkAccessManager(self)
        self.features: dict[Unit, list[QgsFeature]] = {}
        self.units: Units = units
        self.replies: list[QtNetwork.QNetworkReply] = []
        self.unit_finished.connect(
            self.add_unit_to_table, Qt.ConnectionType.QueuedConnection
        )
        self.add_table_headers()

    def add_table_headers(self) -> None:
        table = self.handler.base.ui.tableWidgetDownloadUnits
        table.setColumnCount(3)
        table.setHorizontalHeaderLabels(('ID', 'URL', 'Error'))

    def add_unit_to_table(
        self, url: str, unit_id: str, error_string: str
    ) -> None:
        table = self.handler.base.ui.tableWidgetDownloadUnits
        table.insertRow(0)
        table.setItem(0, 0, get_table_item(unit_id))
        table.setItem(0, 1, get_table_item(url))

        if error_string:
            table.setItem(0, 2, get_table_item(error_string))

        color = QtGui.QColor(
            Qt.GlobalColor.red if error_string else Qt.GlobalColor.green
        )
        color.setAlpha(50)
        color_row(table, 0, color)

    def request(self) -> None:
        self.replies.clear()
        self.handler.clear_download_units_table()
        for unit in self.units:
            reply = self.gisco.get_feature_from_unit(unit, self.nam)
            reply.finished.connect(
                lambda r=reply, u=unit: self._on_finished(r, u)
            )

            # Here we check if reply was finished before we made the connection
            if reply.isFinished():
                self._on_finished(reply, unit)

            self.replies.append(reply)

    def _on_finished(
        self, reply: QtNetwork.QNetworkReply, unit: Unit
    ) -> None:
        self.handle_response(reply, unit)
        reply.deleteLater()
        if len(self.features) == len(self.units):
            self.finished.emit()

    def handle_response(
        self, reply: QtNetwork.QNetworkReply, unit: Unit
    ) -> None:
        features: list[QgsFeature] = []
        url = reply.url().url()
        error: int = reply.error()

        if error == QtNetwork.QNetworkReply.NetworkError.NoError:
            error_string = ''
            data = bytes(reply.readAll()).decode(encoding='UTF-8')
            fields = QgsJsonUtils.stringToFields(data)
            parsed_features = QgsJsonUtils.stringToFeatureList(data, fields)

            # We need to add the _UNIT_ID field which will be used for join
            field_id = QgsField('_UNIT_ID', type=QtCore.QMetaType.Type.QString)
            fields.append(field_id)
            for parsed_feature in parsed_features:
                feature = QgsFeature(fields)
                feature.setGeometry(parsed_feature.geometry())
                feature.setAttributes(parsed_feature.attributes() + [unit.id])
                features.append(feature)
        else:
            error_string = reply.errorString()
        self.features[unit] = features
        self.unit_finished.emit(url, unit.id, error_string)


class GISCOJoinReport(QtWidgets.QDialog):  # type: ignore[misc]  # QDialog is Any without stubs
    def __init__(
        self,
        report_data: JoinReportData | None = None,
        parent: QtWidgets.QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.report_data = report_data
        self.ui = Ui_GISCOJoinReport()
        self.ui.setupUi(self)  # type: ignore[no-untyped-call]  # generated UI module not type-checked

    def add_headers(self) -> None:
        table = self.ui.tableWidgetGISCOJoinReport
        cols = [field.name for field in fields(Unit)]
        cols.insert(0, 'matched')
        table.setColumnCount(len(cols))
        table.setHorizontalHeaderLabels(cols)

    def sort_table(self) -> None:
        table = self.ui.tableWidgetGISCOJoinReport
        table.sortByColumn(0, Qt.SortOrder.DescendingOrder)

    def show(self, event: bool = False) -> None:
        if self.report_data and not self.report_data._shown:
            self.reset_table()
            self.populate_table()
            self.sort_table()
            self.report_data._shown = True
        super().show()

    def reset_table(self) -> None:
        table = self.ui.tableWidgetGISCOJoinReport
        table.sortByColumn(-1, Qt.SortOrder.AscendingOrder)
        table.clear()

    def populate_table(self) -> None:
        table = self.ui.tableWidgetGISCOJoinReport
        assert self.report_data is not None
        table.setRowCount(self.report_data.total)
        self.add_headers()

        for row, code in enumerate(self.report_data.codes):
            unit = self.report_data.units.filter({'id': [code]})
            matched = bool(unit)
            sign = '✔' if matched else '✘'

            table.setItem(row, 0, get_table_item(sign))
            if matched:
                assert len(unit) == 1
                values = astuple(unit[0])
                for col, value in enumerate(values, start=1):
                    table.setItem(row, col, get_table_item(value))
            else:
                table.setItem(row, 1, get_table_item(code))


@dataclass
class JoinReportData:
    total: int
    matched: int
    codes: Sequence[str]
    units: Units
    _shown: bool = False


class GISCOHandler:
    def __init__(self, base: Dialog) -> None:
        self.base = base
        self.unit_downloader: GISCOUnitDownloader | None = None
        self.join_report_data: JoinReportData | None = None
        self.join_report_dialog: GISCOJoinReport = GISCOJoinReport(
            parent=self.base
        )
        self.base.ui.comboBoxGISCOTheme.currentIndexChanged.connect(
            self.add_years
        )
        self.base.ui.comboBoxGISCOYear.currentIndexChanged.connect(
            self.add_spatial_types
        )
        self.base.ui.comboBoxGISCOSpatialType.currentIndexChanged.connect(
            self.add_fields
        )
        self.base.ui.pushButtonGISCOValidateJoin.clicked.connect(
            self.validate_join
        )
        self.base.ui.pushButtonGISCOJoin.clicked.connect(self.join_handler)
        self.base.ui.pushButtonGISCOViewJoinReport.clicked.connect(
            self.join_report_dialog.show
        )
        self.base.ui.pushButtonDatasetInformation.clicked.connect(
            self.show_gisco_dataset_information
        )
        self.themes: dict[str, GISCO] = {}
        self.comboboxes = (
            self.base.ui.comboBoxGISCOTheme,
            self.base.ui.comboBoxGISCOYear,
            self.base.ui.comboBoxGISCOSpatialType,
            self.base.ui.comboBoxGISCOScale,
            self.base.ui.comboBoxGISCOProjection,
        )
        self.add_callback_to_comboboxes(
            lambda: self.base.ui.pushButtonGISCOViewJoinReport.setEnabled(False)
        )

    def show_gisco_dataset_information(self) -> None:
        frame = QDialog(self.base)
        ui = Ui_GISCODatasetInformation()
        ui.setupUi(frame)  # type: ignore[no-untyped-call]  # generated UI module not type-checked
        frame.show()

    def join_handler(self) -> None:
        join_report_enabled = (
            self.base.ui.pushButtonGISCOViewJoinReport.isEnabled()
        )
        if self.base.dataset is None:
            return None
        if not join_report_enabled:
            self.validate_join()
        if not join_report_enabled or self.unit_downloader is None:
            assert self.join_report_data is not None
            units = self.join_report_data.units
            self.unit_downloader = GISCOUnitDownloader(
                self, units, parent=self.base
            )
            if units:
                self.unit_downloader.finished.connect(self.join_data)
                self.unit_downloader.request()
        else:
            self.join_data()

    def add_callback_to_comboboxes(  # type: ignore[explicit-any]  # Callable[..., X] uses `...` which mypy treats as Any; combobox callbacks genuinely accept arbitrary signatures
        self, callback: Callable[..., object]
    ) -> None:
        for combobox in self.comboboxes:
            combobox.currentIndexChanged.connect(callback)

    def join_data(self) -> None:
        assert self.unit_downloader is not None
        features = list(
            itertools.chain.from_iterable(
                self.unit_downloader.features.values()
            )
        )
        if not features:
            return None
        vector_layer = layer_from_features(
            features,
            crs=self.get_projection(),
        )
        table = self.base.converter.table
        processing_result = cast(
            QgsVectorLayer,
            processing.run(
                'native:joinattributestable',
                {
                    'INPUT': vector_layer,
                    'FIELD': '_UNIT_ID',
                    'INPUT_2': table,
                    'FIELD_2': self.base.get_current_table_join_field(),
                    'FIELDS_TO_COPY': [],
                    'METHOD': 0,
                    'DISCARD_NONMATCHING': True,
                    'PREFIX': '',
                    'OUTPUT': 'TEMPORARY_OUTPUT',
                },
            )['OUTPUT'],
        )
        assert self.base.dataset is not None
        processing_result.setName(self.base.dataset.code)
        instance = QgsProject().instance()
        if instance is not None:
            instance.addMapLayer(processing_result)
            canvas = self.base.eurostat_downloader.iface.mapCanvas()
            assert canvas
            canvas.setExtent(processing_result.extent())

    def add_themes(self) -> None:
        # Add themes if not already added
        if not self.base.ui.comboBoxGISCOTheme.count():
            subclasses = [class_.__name__ for class_ in GISCO.__subclasses__()]
            self.base.ui.comboBoxGISCOTheme.addItems(subclasses)

    def cache_theme(self, theme: str) -> None:
        subclasses = GISCO.__subclasses__()
        for i, class_ in enumerate(subclasses):
            if class_.__name__ == theme:
                self.themes[theme] = subclasses[i]()  # type: ignore[abstract]

    def get_theme(self) -> GISCO:
        current_theme = self.base.ui.comboBoxGISCOTheme.currentText()
        if current_theme not in self.themes:
            self.cache_theme(current_theme)
        return self.themes[current_theme]

    @staticmethod
    def clear_comboboxes(comboboxes: Iterable[QtWidgets.QComboBox]) -> None:
        for combobox in comboboxes:
            with QtCore.QSignalBlocker(combobox):
                combobox.clear()

    def add_years(self) -> None:
        self.clear_comboboxes(self.comboboxes[1:])
        initializer = GISCOYearHandler(self.base, self.get_theme())
        initializer.start()

    def add_spatial_types(self, index: int) -> None:
        self.clear_comboboxes(self.comboboxes[2:])
        theme = self.get_theme()
        units = theme.get_units(self.base.ui.comboBoxGISCOYear.itemText(index))
        spatial_types = units.get_unique_field_values(
            field_names=['spatial_type']
        )['spatial_type']
        self.base.ui.comboBoxGISCOSpatialType.addItems(spatial_types)

    def get_units(self) -> Units:
        return self.get_theme().get_units(self.get_year())

    def get_year(self) -> str:
        return cast(str, self.base.ui.comboBoxGISCOYear.currentText())

    def get_projection(self) -> str:
        return cast(str, self.base.ui.comboBoxGISCOProjection.currentText())

    def add_fields(self, index: int) -> None:
        self.base.ui.comboBoxGISCOScale.clear()
        self.base.ui.comboBoxGISCOProjection.clear()
        filters: Mapping[str, Sequence[str]] = {
            'spatial_type': [
                self.base.ui.comboBoxGISCOSpatialType.itemText(index)
            ]
        }
        units = self.get_units()
        filtered = units.filter(filters)
        field_unique_values = filtered.get_unique_field_values(
            field_names=['scale', 'projection']
        )
        self.base.ui.comboBoxGISCOScale.addItems(field_unique_values['scale'])
        self.base.ui.comboBoxGISCOProjection.addItems(
            field_unique_values['projection']
        )

    def clear_download_units_table(self) -> None:
        self.base.ui.tableWidgetDownloadUnits.clearContents()
        self.base.ui.tableWidgetDownloadUnits.setRowCount(0)

    def clear(self) -> None:
        self.base.ui.pushButtonGISCOViewJoinReport.setEnabled(False)
        self.unit_downloader = None
        self.join_report_data = None
        self.clear_download_units_table()

    def validate_join(self) -> None:
        if self.base.dataset is None:
            return None
        self.base.ui.pushButtonGISCOViewJoinReport.setEnabled(True)
        self.join_report_dialog.report_data = self.build_join_report_data()

    def build_join_report_data(self) -> JoinReportData:
        data: DataTableModel = self.base.ui.tableDataset.model()
        geo_column = self.base.ui.comboTableJoinField.currentText()

        # Get unique values from geo column. Geo cells are codes (strings) in
        # practice, so coerce to ``str`` to match :class:`JoinReportData.codes`.
        geo_data: list[str]
        if geo_column in data._columns:
            geo_idx = data._columns.index(geo_column)
            geo_data = list(
                {str(row[geo_idx]) for row in data._data if row[geo_idx] is not None}
            )
        else:
            geo_data = []

        theme = self.get_theme()
        year = self.get_year()
        units = theme.get_units(year)

        filters: Mapping[str, Sequence[str]] = {
            'spatial_type': [
                self.base.ui.comboBoxGISCOSpatialType.currentText()
            ],
            'scale': [self.base.ui.comboBoxGISCOScale.currentText()],
            'projection': [self.base.ui.comboBoxGISCOProjection.currentText()],
            'id': geo_data,
        }

        filtered = units.filter(filters)

        self.join_report_data = JoinReportData(
            len(geo_data), len(filtered), geo_data, filtered
        )
        return self.join_report_data


class GISCOYearHandler(QtCore.QThread):  # type: ignore[misc]  # QThread is Any without stubs
    def __init__(self, base: Dialog, theme: GISCO) -> None:
        self.base = base
        self.theme = theme
        super().__init__(self.base)

    def run(self) -> None:
        years = self.theme.get_years()
        self.base.ui.comboBoxGISCOYear.addItems(years)


class DatabaseInitializer(QtCore.QThread):  # type: ignore[misc]  # QThread is Any without stubs
    error_ocurred = QtCore.pyqtSignal(Exception, name='errorOcurred')

    def __init__(self, base: Dialog) -> None:
        self.base = base
        super().__init__(self.base)

    def run(self) -> None:
        try:
            self.base.ui.treeDatabase.clear()
            self.base.database.initialize_toc()
            if not self.base.database.toc:  # Check if list is empty
                return None
            # Populate the tree with hierarchical data
            self.base.populate_tree(self.base.database.toc)
        except Exception as e:
            self.error_ocurred.emit(e)


class DatasetInitializer(QtCore.QThread):  # type: ignore[misc]  # QThread is Any without stubs
    error_ocurred = QtCore.pyqtSignal(Exception, name='errorOcurred')

    def __init__(self, base: Dialog) -> None:
        self.base = base
        super().__init__(self.base)

    def run(self) -> None:
        try:
            assert self.base.dataset is not None
            self.base.dataset.initialize_data()
            self.base.filterer = DataFilterer(dataset=self.base.dataset)
            self.base.update_model()
        except Exception as e:
            self.error_ocurred.emit(e)


class LoadingLabel(QtCore.QThread):  # type: ignore[misc]  # QThread is Any without stubs
    update_label = QtCore.pyqtSignal(str)

    def __init__(self, label: str, base: QtCore.QObject | None = None) -> None:
        self.base = base
        super().__init__(self.base)
        self.label = label

    def spin(self) -> None:
        for char in itertools.cycle('🌏🌍🌎'):
            self.update_label.emit(f'{self.label}\n{char}  ')
            time.sleep(0.5)
            if self.isInterruptionRequested():
                break

    def run(self) -> None:
        self.spin()


class LoadingDialog(QtWidgets.QDialog):  # type: ignore[misc]  # QDialog is Any without stubs
    def __init__(self, base: QtWidgets.QWidget | None = None) -> None:
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

    def update_loading_label(self, text: str) -> None:
        self.qlabel.setText(text)


class ParameterSectionDialog(QtWidgets.QDialog):  # type: ignore[misc]  # QDialog is Any without stubs
    def __init__(self, base: Dialog, name: str) -> None:
        super().__init__()
        self.base = base
        self.name = name
        self.ui = Ui_ParametersDialog()
        self.ui.setupUi(self)  # type: ignore[no-untyped-call]  # generated UI module not type-checked
        self.filter_toc()
        self.select_based_on_filterer()
        self.section_type_handler()

        # Signals
        self.ui.lineSearch.textChanged.connect(self.filter_list_items)
        self.ui.buttonReset.clicked.connect(self.reset_selection)
        self.ui.listItems.itemSelectionChanged.connect(self.filter_table)

        self.exec()

    def reset_selection(self) -> None:
        self.ui.listItems.clearSelection()

    def filter_toc(self) -> None:
        assert self.base.dataset is not None
        if self.base.dataset.lang is not None:
            names = self.base.dataset.params_info[self.base.dataset.lang][
                self.name
            ]
            assert names is not None
            items = [f'{abbrev} [{name}]' for abbrev, name in names]
        else:
            # Get unique values from column. Cells in this column are
            # :data:`DatasetCell` (``float | str | None``); stringify so that
            # ``QListWidget.addItems`` (which expects ``Iterable[str]``) is
            # satisfied.
            data_dict = self.base.dataset.data
            assert data_dict is not None
            if self.name in data_dict['columns']:
                col_idx = data_dict['columns'].index(self.name)
                values = {
                    str(row[col_idx])
                    for row in data_dict['data']
                    if row[col_idx] is not None
                }
                items = list(values)
            else:
                items = []
        self.ui.listItems.addItems(items)

    def get_listitem_text_abbrev(self, item: QtWidgets.QListWidgetItem) -> str:
        # The string variable inside filter_toc.
        return cast(str, item.text().split(' [')[0])

    def select_based_on_filterer(self) -> None:
        assert self.base.filterer is not None
        if self.name in self.base.filterer.row:
            for row in range(self.ui.listItems.count()):
                item = self.ui.listItems.item(row)
                if item is not None:
                    item.setSelected(
                        self.get_listitem_text_abbrev(item)
                        in self.base.filterer.row[self.name]
                    )

    def get_line_search_text(self) -> str:
        return cast(str, self.ui.lineSearch.text())

    def filter_list_items(self) -> None:
        search_text = self.get_line_search_text().lower()
        for row in range(self.ui.listItems.count()):
            item = self.ui.listItems.item(row)
            if item is not None:
                item_text = item.text().lower()
                item.setHidden(search_text not in item_text)

    def get_selected_items(self) -> list[str]:
        return [
            self.get_listitem_text_abbrev(item)
            for item in self.ui.listItems.selectedItems()
        ]

    def section_type_handler(self) -> None:
        if self.name == (geo_field := self.base.get_current_table_join_field()):
            GeoParameterSectionDialog(section_dialog=self, name=geo_field)

    def filter_table(self) -> None:
        assert self.base.filterer is not None
        if self.name in self.base.filterer.row:
            self.base.filterer.remove_row_filters(filters=self.name)
        if self.get_selected_items():
            self.base.filterer.add_row_filters(
                filters={self.name: self.get_selected_items()}
            )
        self.base.update_model()


class GeoParameterSectionDialog:
    # TODO: maybe add different behaviour for the GEO column later?
    def __init__(self, section_dialog: ParameterSectionDialog, name: str) -> None:
        self.section_dialog = section_dialog
        self.name = name


class TimeSectionDialog(QtWidgets.QDialog):  # type: ignore[misc]  # QDialog is Any without stubs
    def __init__(self, base: Dialog, name: str) -> None:
        super().__init__()
        self.base = base
        self.name = name
        self.ui = Ui_TimePeriodDialog()
        self.ui.setupUi(self)  # type: ignore[no-untyped-call]  # generated UI module not type-checked
        self.add_widgets_to_frames()
        self.add_items_to_combobox()
        self.restore()
        # Signals
        self.add_signals_to_combobox()
        self.ui.buttonReset.clicked.connect(self.set_default)

        self.exec()

    def get_frequency_types(self) -> list[str]:
        assert self.base.dataset is not None
        freq = self.base.dataset.frequency.lower()
        match freq:
            case FrequencyType.ANNUALLY.value:
                return ['Year']
            case FrequencyType.SEMESTERLY.value:
                return ['Year', 'Semester']
            case FrequencyType.QUARTERLY.value:
                return ['Year', 'Quarter']
            case FrequencyType.MONTHLY.value:
                return ['Year', 'Month']
            case FrequencyType.DAILY.value:
                return ['Year', 'Month', 'Day']
            case _:
                raise ValueError(f'No frequency column was found. Unknown {freq}.')

    def add_labels_to_frames(self, frequency: str) -> None:
        def _add_label_to_frames(object_name: str, text: str) -> None:
            for frame in (self.ui.frameStart, self.ui.frameEnd):
                widget = QtWidgets.QLabel(parent=frame, text=text)
                widget.setObjectName(object_name)
                frame.layout().addWidget(widget)
                setattr(frame, object_name, widget)

        frequency = frequency.capitalize()
        label_object_name = ''.join(['label', frequency])
        _add_label_to_frames(object_name=label_object_name, text=frequency)

    def add_combobox_to_frames(self, frequency: str) -> None:
        def _add_combobox_to_frames(object_name: str) -> None:
            for frame in (self.ui.frameStart, self.ui.frameEnd):
                widget = QComboboxCompleter(parent=frame)
                widget.setObjectName(object_name)
                frame.layout().addWidget(widget)
                setattr(frame, object_name, widget)

        frequency = frequency.capitalize()
        combo_object_name = ''.join(['combo', frequency])
        _add_combobox_to_frames(object_name=combo_object_name)

    def add_widgets_to_frames(self) -> None:
        for frequency in self.get_frequency_types():
            self.add_labels_to_frames(frequency)
            self.add_combobox_to_frames(frequency)

    def add_items_to_start_combobox(self) -> None:
        for idx, frequency in enumerate(self.get_frequency_types()):
            widget = self.ui.frameStart.findChild(
                QtWidgets.QComboBox, ''.join(['combo', frequency])
            )
            assert self.base.dataset is not None
            # Split date columns and get unique values for this frequency part
            date_parts = set()
            for date_col in self.base.dataset.date_columns:
                parts = date_col.split('-')
                if idx < len(parts):
                    date_parts.add(parts[idx])
            widget.addItems(sorted(date_parts))

    def add_items_to_end_combobox(self) -> None:
        for idx, frequency in enumerate(self.get_frequency_types()):
            widget = self.ui.frameEnd.findChild(
                QtWidgets.QComboBox, ''.join(['combo', frequency])
            )
            assert self.base.dataset is not None
            # Split date columns and get unique values for this frequency part
            date_parts = set()
            for date_col in self.base.dataset.date_columns:
                parts = date_col.split('-')
                if idx < len(parts):
                    date_parts.add(parts[idx])
            widget.addItems(sorted(date_parts))

    def add_items_to_combobox(self) -> None:
        self.add_items_to_start_combobox()
        self.add_items_to_end_combobox()

    def add_signals_to_combobox(self) -> None:
        for frame in (self.ui.frameStart, self.ui.frameEnd):
            widgets = frame.findChildren(QtWidgets.QComboBox)
            for widget in widgets:
                widget.currentIndexChanged.connect(self.add_time_filters)

    def get_start_time_combobox(self) -> str:
        times: list[str] = []
        for frequency in self.get_frequency_types():
            widget = self.ui.frameStart.findChild(
                QtWidgets.QComboBox, ''.join(['combo', frequency])
            )
            times.append(widget.currentText())
        return '-'.join(times)

    def get_end_time_combobox(self) -> str:
        times: list[str] = []
        for frequency in self.get_frequency_types():
            widget = self.ui.frameEnd.findChild(
                QtWidgets.QComboBox, ''.join(['combo', frequency])
            )
            times.append(widget.currentText())
        return '-'.join(times)

    def add_time_filters(self) -> None:
        assert self.base.dataset is not None
        assert self.base.filterer is not None
        cols = list(self.base.dataset.date_columns)
        try:
            start = cols.index(self.get_start_time_combobox())
        except ValueError:
            start = 0
        try:
            end = cols.index(self.get_end_time_combobox())
        except ValueError:
            end = len(cols) - 1
        cols_filtered = cols[start : end + 1]
        cols = self.base.dataset.params + cols_filtered
        self.base.filterer.set_column_filters(filters=cols)
        self.base.update_model()

    def set_default_start_combobox(self) -> None:
        for idx, frequency in enumerate(self.get_frequency_types()):
            widget = self.ui.frameStart.findChild(
                QtWidgets.QComboBox, ''.join(['combo', frequency])
            )
            assert self.base.dataset is not None
            # Get first date column and extract the part for this frequency
            if self.base.dataset.date_columns:
                first_col = self.base.dataset.date_columns[0]
                parts = first_col.split('-')
                if idx < len(parts):
                    items_first = parts[idx]
                    # Find index in widget
                    default_index = widget.findText(items_first)
                    if default_index >= 0:
                        widget.setCurrentIndex(default_index)

    def set_default_end_combobox(self) -> None:
        for idx, frequency in enumerate(self.get_frequency_types()):
            widget = self.ui.frameEnd.findChild(
                QtWidgets.QComboBox, ''.join(['combo', frequency])
            )
            assert self.base.dataset is not None
            # Get last date column and extract the part for this frequency
            if self.base.dataset.date_columns:
                last_col = self.base.dataset.date_columns[-1]
                parts = last_col.split('-')
                if idx < len(parts):
                    items_last = parts[idx]
                    # Find index in widget
                    default_index = widget.findText(items_last)
                    if default_index >= 0:
                        widget.setCurrentIndex(default_index)

    def set_default(self) -> None:
        self.set_default_start_combobox()
        self.set_default_end_combobox()
        self.add_time_filters()

    def restore_start_combobox(self) -> None:
        assert self.base.filterer is not None
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

    def restore_end_combobox(self) -> None:
        assert self.base.filterer is not None
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

    def restore(self) -> None:
        self.restore_start_combobox()
        self.restore_end_combobox()


class SettingsDialog(QtWidgets.QDialog):  # type: ignore[misc]  # QDialog is Any without stubs
    def __init__(
        self,
        base: Dialog,
    ) -> None:
        super().__init__()
        self.base = base
        self.ui = Ui_SettingsDialog()
        self.ui.setupUi(self)  # type: ignore[no-untyped-call]  # generated UI module not type-checked

        # TODO: maybe make an abstraction instead of
        # hardcoding the checkboxes?
        # e.g. filter the self.ui__dict__ by
        # the attributes starting with 'checkBoxAgency'
        self._agencies_checkboxes: dict[Agency, QtWidgets.QCheckBox] = {
            Agency.COMEXT: self.ui.checkBoxAgencyCOMEXT,
            Agency.COMP: self.ui.checkBoxAgencyCOMP,
            Agency.EMPL: self.ui.checkBoxAgencyEMPL,
            Agency.EUROSTAT: self.ui.checkBoxAgencyEUROSTAT,
            Agency.GROW: self.ui.checkBoxAgencyGROW,
        }
        assert all(agency in self._agencies_checkboxes for agency in Agency), (
            'Update the agency global settings combobox dict'
        )

        self.restore_global_settings()
        ok_btn = self.ui.buttonBox.button(QtWidgets.QDialogButtonBox.StandardButton.Ok)
        ok_btn.clicked.connect(self.update_global_settings)
        self.exec()

    def update_global_settings(self) -> None:
        # Agencies
        agencies_checkboxes_bool: dict[Agency, bool] = {
            k: v.isChecked() for k, v in self._agencies_checkboxes.items()
        }
        selected_agencies = [
            agency
            for agency, checked in agencies_checkboxes_bool.items()
            if checked
        ]
        if not selected_agencies:
            selected_agencies = list(Agency)
        GLOBAL_SETTINGS.agencies = selected_agencies

    def restore_global_settings(self) -> None:
        # Restore agency settings
        if GLOBAL_SETTINGS.agencies:
            for agency, checkbox in self._agencies_checkboxes.items():
                if agency not in GLOBAL_SETTINGS.agencies:
                    checkbox.setChecked(False)


@dataclass
class DataFilterer:
    dataset: Dataset
    row: dict[str, list[DatasetCell]] = field(init=False, default_factory=dict)
    column: list[str] = field(init=False, default_factory=list)

    def __post_init__(self) -> None:
        assert self.dataset.data is not None
        self.column = list(self.dataset.data['columns'])

    @property
    def data_dict(self) -> DatasetPayload:
        assert self.dataset.data is not None
        return self.dataset.data

    @property
    def date_columns(self) -> list[str]:
        return [col for col in self.column if col not in self.dataset.params]

    def apply_filters(self) -> DatasetPayload:
        """Apply row and column filters, return filtered data dict."""
        data = self.data_dict
        columns = data['columns']
        rows = data['data']

        # Build column indices for selected columns
        col_indices = [
            columns.index(col) for col in self.column if col in columns
        ]

        # Filter rows based on row filters
        filtered_rows: list[list[DatasetCell]] = []
        for row in rows:
            include = True
            for col, vals in self.row.items():
                if not vals:
                    continue
                if col not in columns:
                    continue
                col_idx = columns.index(col)
                if row[col_idx] not in vals:
                    include = False
                    break
            if include:
                # Only include selected columns
                filtered_row = [row[idx] for idx in col_indices]
                filtered_rows.append(filtered_row)

        # Build filtered column names
        filtered_columns = [columns[idx] for idx in col_indices]

        return {'columns': filtered_columns, 'data': filtered_rows}

    def add_row_filters(
        self, filters: Mapping[str, Iterable[DatasetCell]]
    ) -> None:
        # This is only for the row axis
        for col, values in filters.items():
            for value in values:
                self.row.setdefault(col, []).append(value)

    def set_column_filters(
        self, filters: None | str | Iterable[str] = None
    ) -> None:
        if filters is None:
            assert self.dataset.data is not None
            filters = list(self.dataset.data['columns'])
        elif isinstance(filters, str):
            filters = [filters]
        self.column = list(filters)

    def remove_row_filters(
        self,
        filters: None
        | str
        | dict[str, Iterable[DatasetCell]]
        | Iterable[str] = None,
    ) -> None:
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

    def remove_column_filters(self, filters: str | Iterable[str]) -> None:
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
    def table_model(self) -> DataTableModel:
        return DataTableModel(data=self.filterer.apply_filters())


class DataTableModel(QtCore.QAbstractTableModel):  # type: ignore[misc]  # QAbstractTableModel is Any without stubs
    """Qt table model using dict data instead of pandas DataFrame."""

    def __init__(
        self,
        data: DatasetPayload,
        parent: QtCore.QObject | None = None,
    ) -> None:
        QtCore.QAbstractTableModel.__init__(self, parent)
        self._columns: list[str] = data['columns']
        self._data: list[list[DatasetCell]] = data['data']

    def rowCount(self, parent: object = None) -> int:
        return len(self._data)

    def columnCount(self, parent: object = None) -> int:
        return len(self._columns)

    def data(
        self,
        index: QtCore.QModelIndex,
        role: int = QtCore.Qt.ItemDataRole.DisplayRole,
    ) -> str | None:
        if index.isValid():
            if role == QtCore.Qt.ItemDataRole.DisplayRole:
                value = self._data[index.row()][index.column()]
                return '' if value is None else str(value)
        return None

    def headerData(
        self,
        col: int,
        orientation: QtCore.Qt.Orientation,
        role: int,
    ) -> str | None:
        if (
            orientation == QtCore.Qt.Orientation.Horizontal
            and role == QtCore.Qt.ItemDataRole.DisplayRole
        ):
            return self._columns[col]
        return None


def get_combobox_items(combobox: QtWidgets.QComboBox) -> list[str]:
    return [combobox.itemText(idx) for idx in range(combobox.count())]


class Exporter:
    base: Dialog

    def __init__(self, base: Dialog) -> None:
        self.base = base

    def add_table(self) -> None:
        if self.base.dataset is None:
            return None
        table = self.base.converter.table
        table.setName(self.base.dataset.code)
        QgsProject.instance().addMapLayer(table)


class JoinHandler:
    base: Dialog

    def __init__(self, base: Dialog) -> None:
        self.base = base

    @property
    def join_info(self) -> QgsVectorLayerJoinInfo:
        return self.get_join_info()

    def get_join_info(self) -> QgsVectorLayerJoinInfo:
        table = self.base.converter.table
        QgsProject.instance().addMapLayer(table)
        join_info = QgsVectorLayerJoinInfo()
        join_info.setJoinFieldName(
            self.base.ui.comboTableJoinField.currentText()
        )
        join_info.setTargetFieldName(
            self.base.ui.qgsComboLayerJoinField.currentText()
        )
        assert self.base.dataset is not None
        join_info.setJoinFieldNamesSubset(
            itertools.chain(
                self.base.ui.comboBoxColumnsToJoin.currentData(),
                self.base.dataset.date_columns,
            )
        )
        join_info.setJoinLayerId(table.id())
        join_info.setUsingMemoryCache(True)
        join_info.setJoinLayer(table)
        join_info.setPrefix(self.base.ui.linePrefix.text())
        return join_info

    def join_table_to_layer(self) -> None:
        current_layer = self.base.ui.qgsComboLayer.currentLayer()
        if self.base.dataset is None or current_layer is None:
            return None
        current_layer.addJoin(self.join_info)


class QgsConverter:
    base: Dialog

    def __init__(self, base: Dialog) -> None:
        self.base = base

    @property
    def table(self) -> QgsVectorLayer:
        return self.from_data_dict(
            self.base.model.table_model._data,
            self.base.model.table_model._columns,
        )

    @staticmethod
    def dtype_mapper(
        values: Sequence[DatasetCell],
    ) -> QtCore.QMetaType.Type:
        """Infer QMetaType type from list of values."""
        sample = None
        for val in values:
            if val is not None and val != '':
                sample = val
                break

        if sample is None:
            return QtCore.QMetaType.Type.QString

        if isinstance(sample, bool):
            return QtCore.QMetaType.Type.Bool
        elif isinstance(sample, int):
            return QtCore.QMetaType.Type.Int
        elif isinstance(sample, float):
            return QtCore.QMetaType.Type.Double
        else:
            try:
                float(str(sample))
                if '.' in str(sample):
                    return QtCore.QMetaType.Type.Double
                else:
                    return QtCore.QMetaType.Type.Int
            except (ValueError, TypeError):
                return QtCore.QMetaType.Type.QString

    @staticmethod
    def to_data_dict(
        layer: QgsVectorLayer,
    ) -> LayerPayload:
        """Convert QGIS vector layer to data dict."""
        columns = [field.name() for field in layer.fields()]
        data: list[list[object]] = [
            list(feat.attributes()) for feat in layer.getFeatures()
        ]
        return {'columns': columns, 'data': data}

    def from_data_dict(
        self,
        data: Sequence[Sequence[DatasetCell]],
        columns: Sequence[str],
    ) -> QgsVectorLayer:
        """Method to convert data dict to a qgis table layer."""
        assert self.base.dataset is not None
        temp = QgsVectorLayer('none', self.base.dataset.code, 'memory')
        temp_data = temp.dataProvider()
        temp.startEditing()
        attributes: list[QgsField] = []

        # Transpose data to get columns
        num_cols = len(columns)
        col_values: list[list[DatasetCell]] = [[] for _ in range(num_cols)]
        for row in data:
            for col_idx in range(min(len(row), num_cols)):
                col_values[col_idx].append(row[col_idx])

        # Create fields with inferred types
        for col_idx, col_name in enumerate(columns):
            field_type = self.dtype_mapper(col_values[col_idx])
            attributes.append(QgsField(col_name, field_type))

        temp_data.addAttributes(attributes)
        temp.updateFields()

        # Add features
        rows: list[QgsFeature] = []
        for row_data in data:
            f = QgsFeature()
            f.setAttributes(row_data)
            rows.append(f)
        temp_data.addFeatures(rows)
        temp.commitChanges()
        return temp
