import eurostat as _eurostat

from typing import Any

from .settings import GLOBAL_SETTINGS


__all__ = ['eurostat']


def _set_eurostat_proxy() -> None:
    if GLOBAL_SETTINGS.proxy is None:
        return None
    if GLOBAL_SETTINGS.proxy.host and GLOBAL_SETTINGS.proxy.port:
        # Create a dictionary with the proxy information
        proxy = (
            f'http://{GLOBAL_SETTINGS.proxy.host}:{GLOBAL_SETTINGS.proxy.port}'
        )
        proxy_info = {
            'https': [
                GLOBAL_SETTINGS.proxy.user,
                GLOBAL_SETTINGS.proxy.password,
                proxy
            ]
        }
        # Set the proxy for the eurostat library
        _eurostat.setproxy(proxy_info)  # type: ignore
    else:
        # if not host and port, we have to remove the existing
        # proxy settings. this is the best way I could think of.
        args = _eurostat.get_requests_args()
        try:
            args.pop('proxies')
        except KeyError:
            return None


def _set_eurostat_args() -> None:
    _set_eurostat_proxy()
    _eurostat.set_requests_args(  # type: ignore
        verify=GLOBAL_SETTINGS.verify_ssl
    )


class _eurostat_wrapper:
    """A wrapper for the eurostat package.

    This wrapper allows to call 'set_eurostat_args'
    every time an objectfrom the eurostat module is
    accessed. This way, the latest global settings
    (e.g. SSL verification setting from the GUI settings dialog)
    are used.
    """
    def __getattribute__(self, name: str) -> Any:
        _set_eurostat_args()
        print(GLOBAL_SETTINGS)
        return object.__getattribute__(_eurostat, name)


eurostat = _eurostat_wrapper()
