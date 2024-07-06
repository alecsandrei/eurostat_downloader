"""This script initializes the plugin, making it known to QGIS."""
import sys
import site

from qgis.core import Qgis

from .src.modules import MODULES_INSTALL_FOLDER
from .src.modules import (
    get_reqs,
    get_modules,
    check_if_missing,
    MissingModulesDialog,
    State
)


MissingModules = list[str]


def pip_missing() -> bool:
    """Returns true if pip is not installed."""
    modules = get_modules()
    if not any(module.name == 'pip' for module in modules):
        return True
    return False


def handle_missing_modules() -> None | MissingModules:

    def get_module_states():
        reqs = get_reqs()
        return check_if_missing(reqs)

    modules = get_module_states()
    if not all(module.state is State.FOUND for module in modules):
        dialog = MissingModulesDialog(modules)
        dialog.exec_()

    modules = get_module_states()
    if not all(module.state is State.FOUND for module in modules):
        return (
            [module.module.name for module in modules
             if module.state is not State.FOUND]
        )


def classFactory(iface):
    """Load EurostatDownloader class from file EurostatDownloader.

    :param iface: A QGIS interface instance.
    :type iface: QgsInterface
    """
    if MODULES_INSTALL_FOLDER.as_posix() not in sys.path:
        # sys.path.insert(-1, MODULES_INSTALL_FOLDER.as_posix())
        site.addsitedir(MODULES_INSTALL_FOLDER.as_posix())
    missing_modules = handle_missing_modules()
    if missing_modules is not None:
        if pip_missing():
            message = (
                'Python "pip" was not found and the required packages '
                'could not be installed. The Eurostat Downloader plugin '
                'will not work.'
            )
            (iface
            .messageBar()
            .pushMessage('ERROR', message,
                        level=Qgis.MessageLevel.Critical)
            )
        message = (
            'The following packages were not found '
            f'or could not be installed: {", ".join(missing_modules)}. '
            'The Eurostat Downloader plugin might not work.'
        )
        (iface
        .messageBar()
        .pushMessage('ERROR', message,
                    level=Qgis.MessageLevel.Critical)
        )
    from .eurostat_downloader import EurostatDownloader
    return EurostatDownloader(iface)
