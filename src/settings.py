from __future__ import annotations

from typing import NamedTuple
from dataclasses import (
    dataclass,
    field
)

from qgis.core import (
    QgsNetworkAccessManager,
    QgsSettings
)

from .enums import Agency


class ProxySettings(NamedTuple):
    host: str
    port: str
    user: None | str
    password: None | str


def _get_qgis_proxy() -> None | ProxySettings:
    # This function was taken from the QuickMapServices plugin.
    # module https://github.com/nextgis/quickmapservices/blob/master/src/qgis_settings.py  # noqa
    proxy_enabled = QGS_SETTINGS.value('proxy/proxyEnabled', u'', type=unicode)
    proxy_type = QGS_SETTINGS.value('proxy/proxyType', u'', type=unicode)
    proxy_host = QGS_SETTINGS.value('proxy/proxyHost', u'', type=unicode)
    proxy_port = QGS_SETTINGS.value('proxy/proxyPort', u'', type=unicode)
    proxy_user = QGS_SETTINGS.value('proxy/proxyUser', u'', type=unicode)
    proxy_password = QGS_SETTINGS.value('proxy/proxyPassword', u'', type=unicode)

    if proxy_enabled == 'true':
        if proxy_type == 'DefaultProxy':
            qgsNetMan = QgsNetworkAccessManager.instance()
            proxy = qgsNetMan.proxy().applicationProxy()
            proxy_host = proxy.hostName()
            proxy_port = str(proxy.port())
            proxy_user = proxy.user()
            proxy_password = proxy.password()

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


@dataclass
class GlobalSettings:
    qgs_settings: QgsSettings
    proxy: ProxySettings | None = None
    agencies: list[Agency] = field(default_factory=list)
    verify_ssl: bool = True

    def __post_init__(self):
        self.agencies = list(Agency)
        self.proxy = _get_qgis_proxy()


QGS_SETTINGS = QgsSettings()
GLOBAL_SETTINGS = GlobalSettings(qgs_settings=QGS_SETTINGS)
