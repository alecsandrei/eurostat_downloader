from PyQt5 import QtCore
from PyQt5 import QtWidgets

from pandas import DataFrame



class PyQtUtils:
    """Utilities for the graphical user interface."""
    
    @staticmethod
    def get_x_y_height(widget: QtWidgets.QWidget):
        pos = widget.pos()
        x = pos.x()
        y = pos.y()
        height = widget.height()
        return x, y, height
    
    class PandasModel(QtCore.QAbstractTableModel):
        """Class to turn a pandas dataframe into a QAbstractTableModel."""
        def __init__(self, data: DataFrame, parent=None):
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