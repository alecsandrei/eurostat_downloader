from __future__ import annotations

from typing import (
    NamedTuple,
    TYPE_CHECKING,
    TypedDict
)
from dataclasses import dataclass

from qgis.core import QgsNetworkAccessManager

if TYPE_CHECKING:
    from qgis.core import QgsSettings
    from .data import Agency


@dataclass
class GlobalSettings:
    proxy: ProxySettings | None = None
    agencies: list[Agency] | None = None
    verify_ssl: bool | None = None


GLOBAL_SETTINGS = GlobalSettings()


class ProxySettings(NamedTuple):
    host: str
    port: str
    user: None | str
    password: None | str


def get_qgis_proxy(s: QgsSettings) -> None | ProxySettings:
    # This function was taken from the QuickMapServices plugin.
    # module https://github.com/nextgis/quickmapservices/blob/master/src/qgis_settings.py  # noqa
    proxy_enabled = s.value('proxy/proxyEnabled', u'', type=unicode)
    proxy_type = s.value('proxy/proxyType', u'', type=unicode)
    proxy_host = s.value('proxy/proxyHost', u'', type=unicode)
    proxy_port = s.value('proxy/proxyPort', u'', type=unicode)
    proxy_user = s.value('proxy/proxyUser', u'', type=unicode)
    proxy_password = s.value('proxy/proxyPassword', u'', type=unicode)

    if proxy_enabled == 'true':
        if proxy_type == 'DefaultProxy':
            qgsNetMan = QgsNetworkAccessManager.instance()
            proxy = qgsNetMan.proxy().applicationProxy()
            proxy_host = proxy.hostName()
            proxy_port = str(proxy.port())
            proxy_user = proxy.user()
            if not proxy_user:
                proxy_user = None
            proxy_password = proxy.password()
            if not proxy_password:
                proxy_password = None

        if proxy_type in [
            'DefaultProxy', 'Socks5Proxy', 'HttpProxy', 'HttpCachingProxy'
        ]:
            return ProxySettings(
                proxy_host,
                proxy_port,
                proxy_user,
                proxy_password
            )

    return None
