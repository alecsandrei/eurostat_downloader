from __future__ import annotations

from typing import Any
import importlib

from .settings import GLOBAL_SETTINGS
from .modules import MODULES_INSTALL_FOLDER


__all__ = ['eurostat']


class _EurostatLoader:
    """A wrapper for the 'eurostat' package.

    This wrapper allows to call 'set_eurostat_args'
    every time an objectfrom the eurostat module is
    accessed. This way, the latest global settings
    (e.g. SSL verification setting from the GUI settings dialog)
    are used. It also loads 'eurostat' lazly.
    """

    def __init__(self):
        self._mod = None

    def _set_eurostat_proxy(self) -> None:
        assert self._mod is not None
        if GLOBAL_SETTINGS.proxy is None:
            return None
        if GLOBAL_SETTINGS.proxy.host and GLOBAL_SETTINGS.proxy.port:
            # Create a dictionary with the proxy information
            proxy = (
                f'http://{GLOBAL_SETTINGS.proxy.host}:{GLOBAL_SETTINGS.proxy.port}'  # noqa
            )
            proxy_info = {
                'https': [
                    GLOBAL_SETTINGS.proxy.user,
                    GLOBAL_SETTINGS.proxy.password,
                    proxy
                ]
            }
            # Set the proxy for the eurostat library
            self._mod.setproxy(proxy_info)  # type: ignore
        else:
            # if not host and port, we have to remove the existing
            # proxy settings. this is the best way I could think of.
            args = self._mod.get_requests_args()
            try:
                args.pop('proxies')
            except KeyError:
                return None

    def _set_eurostat_args(self) -> None:
        assert self._mod is not None
        self._set_eurostat_proxy()
        self._mod.set_requests_args(  # type: ignore
            verify=GLOBAL_SETTINGS.verify_ssl
        )

    def __getattr__(self, name: str) -> Any:
        if self._mod is None:
            self._mod = importlib.import_module('eurostat')
        self._set_eurostat_args()
        return getattr(self._mod, name)


eurostat = _EurostatLoader()
