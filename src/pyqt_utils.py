from PyQt5 import QtWidgets
from PyQt5 import QtCore


class PandasModel(QtCore.QAbstractTableModel):
    """
    Class to populate a table view with a pandas dataframe
    """
    def __init__(self, data, parent=None):
        QtCore.QAbstractTableModel.__init__(self, parent)
        self._data = data

    def rowCount(self, parent=None):
        return self._data.shape[0]

    def columnCount(self, parent=None):
        return self._data.shape[1]

    def data(self, index, role=QtCore.Qt.DisplayRole):
        if index.isValid():
            if role == QtCore.Qt.DisplayRole:
                return str(self._data.iloc[index.row(), index.column()])
        return None

    def headerData(self, col, orientation, role):
        if orientation == QtCore.Qt.Horizontal and role == QtCore.Qt.DisplayRole:
            return self._data.columns[col]
        return None


class GuiUtils:
    """
    Utilities for the graphical user interface
    """
    @staticmethod
    def get_x_y_height(widget):
        pos = widget.pos()
        x = pos.x()
        y = pos.y()
        height = widget.height()
        return x, y, height
    
    @staticmethod
    def combobox_add_completer(combobox: QtWidgets.QComboBox):
        combobox.setEditable(True)
        combobox.setInsertPolicy(QtWidgets.QComboBox.NoInsert)
        combobox.completer().setCompletionMode(QtWidgets.QCompleter.PopupCompletion)
        return combobox
    

