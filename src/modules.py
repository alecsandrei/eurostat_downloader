"""Helps with installing the missing modules in the requirements.txt file."""

from __future__ import annotations

import itertools
import sys
import subprocess
from collections.abc import Iterable
from pathlib import Path
from enum import Enum, auto
from typing import NamedTuple
import pkgutil
import importlib.metadata
import platform

from qgis.core import QgsApplication
from qgis.PyQt import (
    QtWidgets,
    QtCore,
    QtGui
)

from .ui import MissingModules


QGS_PREFIX_PATH = Path(QgsApplication.prefixPath())
PY_VERSION = platform.python_version_tuple()

if sys.platform == 'win32':
    PY_EXECUTABLE = QGS_PREFIX_PATH.parent / f'Python{PY_VERSION[0]}{PY_VERSION[1]}' / 'python.exe'  # noqa
elif sys.platform == 'linux':
    PY_EXECUTABLE = QGS_PREFIX_PATH / 'bin' / F'python{PY_VERSION[0]}.{PY_VERSION[1]}'  # noqa
elif sys.platform == 'darwin':
    # TODO I have no idea what to do for Mac OS here. can someone help out?
    # I will keep same as linux until someone contributes
    # The goal is to have PY_EXECUTABLE point to the python executable
    PY_EXECUTABLE = QGS_PREFIX_PATH / 'bin' / 'python'


REQUIREMENTS_FILE = Path(__file__).parent.parent / 'requirements.txt'
MODULES_INSTALL_FOLDER = Path(__file__).parent.parent / 'extlibs'


class Color(Enum):
    RED = (255, 0, 0)
    GREEN = (0, 255, 0)


def get_modules():
    return list(pkgutil.iter_modules())


class State(Enum):
    FOUND = auto()
    NOT_FOUND = auto()
    WRONG_VERSION = auto()

    def to_user_text(self):
        return (
            self.name
            .capitalize()
            .replace('_', ' ')
        )


class ComparisonOperator(Enum):
    EQUAL = '=='
    GE = '>='
    LE = '<='


class Version(NamedTuple):
    major: int
    minor: int | None
    patch: int | None

    def __str__(self) -> str:
        return '.'.join([str(val) for val in self])

    @staticmethod
    def from_string(string: str):
        vals: list[int | None] = [int(substr) for substr in string.split('.')]
        assert isinstance(vals[0], int)
        # Fill vals up to 3. NOTE: Is there a better way?
        vals.extend(itertools.repeat(None, 3 - len(vals)))
        # Mypy is not happy with star unpack here.
        return Version(
            vals[0], vals[1], vals[2]
        )


class ModuleRequired(NamedTuple):
    name: str
    operator: ComparisonOperator | None
    version: Version | None


class ModuleState(NamedTuple):
    module: ModuleRequired
    state: State
    version_found: Version | None


Requirements = list[ModuleRequired]


def get_reqs() -> Requirements:
    """Parses requirements.txt file."""
    requirements: Requirements = []
    with open(
        REQUIREMENTS_FILE, mode='r', encoding='UTF-8'
    ) as requirements_file:
        for line in requirements_file:
            line = line.strip()
            try:
                line = line[:line.index('#')]
            except ValueError:
                ...
            line = ''.join([char for char in line if not char.isspace()])
            if not line:
                continue
            # NOTE: only support ==, <= and >=
            if not any(
                operator.value in line for operator in ComparisonOperator
            ):
                requirements.append(
                    ModuleRequired(line, None, None)
                )
                continue
            for operator in ComparisonOperator:
                if (operator_val := operator.value) not in line:
                    continue
                operator_idx = line.index(operator_val)
                module_name = line[:operator_idx]
                version = Version.from_string(
                    line[operator_idx + len(operator_val):]
                )
                requirements.append(
                    ModuleRequired(module_name, operator, version)
                )
        return requirements


Modules = list[ModuleState]
ReturnCode = int
TableRow = int


def check_if_missing(requirements: Requirements) -> Modules:
    modules: Modules = []
    module_names = [module.name for module in get_modules()]
    for req in requirements:
        if req.name not in module_names:
            modules.append(
                ModuleState(req, State.NOT_FOUND, None)
            )
        elif req.version is None:
            modules.append(
                ModuleState(req, State.FOUND, None)
            )
        else:
            found_version = Version.from_string(
                importlib.metadata.version(req.name)
            )
            version_matches = False
            if req.operator is ComparisonOperator.EQUAL:
                version_matches = found_version == req.version
            elif req.operator is ComparisonOperator.GE:
                version_matches = found_version >= req.version
            elif req.operator is ComparisonOperator.LE:
                version_matches = found_version <= req.version
            if not version_matches:
                modules.append(
                    ModuleState(req, State.WRONG_VERSION, found_version)
                )
            else:
                modules.append(
                    ModuleState(req, State.FOUND, found_version)
                )
    return modules


class MissingModulesDialog(QtWidgets.QDialog):

    def __init__(self, modules: Modules):
        super().__init__()

        # Init GUI
        self.ui = MissingModules()
        self.ui.setupUi(self)
        self.module_states = modules
        self.fill_table()
        self.ui.pushButtonInstall.clicked.connect(self.install_missing_modules)
        self.ui.pushButtonLetUserInstall.clicked.connect(self.close)
        self.ui.pushButtonExportLogs.clicked.connect(self.export_logs)
        self.ui.tabWidgetMain.setCurrentIndex(0)

    def fill_table(self):
        self.ui.tableWidgetModules.setRowCount(len(self.module_states))
        for i, module_state in enumerate(self.module_states):
            name = module_state.module.name
            version_required = str(module_state.module.version)
            version_found = str(module_state.version_found)
            state = module_state.state.to_user_text()
            operator = (
                operator.value
                if (operator := module_state.module.operator) is not None
                else ''
            )
            row_values = (
                name,
                f'{operator}{version_required}',
                version_found,
                state
            )
            for j, value in enumerate(row_values):
                self.ui.tableWidgetModules.setItem(
                    i, j, QtWidgets.QTableWidgetItem(value)
                )

    def export_logs(self):
        file_dialog = QtWidgets.QFileDialog(self)
        file_name, _ = file_dialog.getSaveFileName(
            self, 'Save Logs', '', 'All Files(*);;Text Files(*.txt)'
        )
        if file_name:
            with open(file_name, 'w') as f:
                f.write(self.ui.labelLogs.text())

    def handle_completed_modules(
        self,
        table_row: int,
        return_code: int | None
    ):
        if return_code is None:
            return None
        color = Color.GREEN if return_code == 0 else Color.RED
        for col in range(self.ui.tableWidgetModules.columnCount()):
            (
                self.ui
                .tableWidgetModules
                .item(table_row, col)
                .setBackground(QtGui.QColor(*color.value))
            )

    def install_missing_modules(self):
        if not MODULES_INSTALL_FOLDER.exists():
            MODULES_INSTALL_FOLDER.mkdir()
        installer = MissingModulesInstaller(
            self,
            self.module_states,
        )
        installer.started.connect(
            lambda: self.ui.tabWidgetMain.setCurrentWidget(self.ui.tabLogs)
        )
        installer.subprocess_result.connect(self.handle_completed_modules)
        installer.finished.connect(
            lambda: self.ui.labelProcessFinished.setText(
                ('Process finished. You can close the window now.')
            )
        )
        installer.start()


class MissingModulesInstaller(QtCore.QThread):

    subprocess_result = QtCore.pyqtSignal(int, int)

    def __init__(
        self,
        base: MissingModulesDialog,
        module_states: Iterable[ModuleState],
    ):
        self.base = base
        super().__init__(self.base)
        self.ui = self.base.ui
        self.module_states = module_states

    def run(self):
        for table_row, module_state in enumerate(self.module_states):
            if module_state.state is State.FOUND:
                continue
            name = module_state.module.name
            operator = module_state.module.operator
            version = module_state.module.version
            if operator is not None and version is not None:
                name = ''.join([name, operator.value, str(version)])
            startupinfo = None
            if sys.platform == 'win32':
                startupinfo = subprocess.STARTUPINFO()  # type: ignore
                startupinfo.dwFlags |= (
                    subprocess.STARTF_USESHOWWINDOW  # type: ignore
                )
            try:
                completed_process = subprocess.Popen([
                    PY_EXECUTABLE.as_posix(),
                    '-m',
                    'pip',
                    'install',
                    '-t',
                    MODULES_INSTALL_FOLDER.as_posix(),
                    name,
                ],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    startupinfo=startupinfo
                )
            except Exception as e:
                raise e
            # Normally, return_code should never be emitted as None
            return_code = None
            while True:
                if completed_process.stdout is None:
                    break
                line = completed_process.stdout.readline()
                line_str = line.decode(encoding='utf-8').strip()
                if line_str:
                    new_text = ''.join([
                        self.ui.labelLogs.text().strip(),
                        f'\n{line_str}'
                    ])
                    self.ui.labelLogs.setText(new_text)
                    vbar = self.ui.scrollAreaLogs.verticalScrollBar()
                    vbar.setValue(vbar.maximum())
                if (return_code := completed_process.poll()) is not None:
                    # if the return code is not 0, then append the standard
                    # error to the logs
                    if (
                        return_code != 0
                        and completed_process.stderr is not None
                    ):
                        text_to_append = '\n'.join([
                            line.decode('utf-8').strip() for line
                            in completed_process.stderr.readlines()
                        ])
                        new_text = ''.join([
                            self.ui.labelLogs.text().strip(),
                            f'\n{text_to_append}'
                        ])
                        self.ui.labelLogs.setText(new_text)
                    break
            self.subprocess_result.emit(table_row, return_code)
