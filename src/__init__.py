import eurostat
from qgis.PyQt.QtCore import QSettings
from qgis.core import QgsNetworkAccessManager



SETTINGS = QSettings()

def get_qgis_proxy(s: QSettings):
    # This function was taken from the QuickMapServices plugin.
    proxy_enabled = s.value("proxy/proxyEnabled", u"", type=unicode)
    proxy_type = s.value("proxy/proxyType", u"", type=unicode)
    proxy_host = s.value("proxy/proxyHost", u"", type=unicode)
    proxy_port = s.value("proxy/proxyPort", u"", type=unicode)
    proxy_user = s.value("proxy/proxyUser", u"", type=unicode)
    proxy_password = s.value("proxy/proxyPassword", u"", type=unicode)

    if proxy_enabled == "true":
        if proxy_type == "DefaultProxy":
            qgsNetMan = QgsNetworkAccessManager.instance()
            proxy = qgsNetMan.proxy().applicationProxy()
            proxy_host = proxy.hostName()
            proxy_port = str(proxy.port())
            proxy_user = proxy.user()
            proxy_password = proxy.password()

        if proxy_type in ["DefaultProxy", "Socks5Proxy", "HttpProxy", "HttpCachingProxy"]:
            return (
                proxy_host,
                proxy_port,
                proxy_user,
                proxy_password
            )

    return ("", "", "", "")


proxy_host, proxy_port, proxy_user, proxy_password = get_qgis_proxy(s=SETTINGS)

if not proxy_user:
    proxy_user = None
    
if not proxy_password:
    proxy_password = None

if proxy_host and proxy_port:
    # Create a dictionary with the proxy information
    proxy_info = {
        'https': [proxy_user, proxy_password, f'http://{proxy_host}:{proxy_port}']
    }
    # Set the proxy for the eurostat library
    eurostat.setproxy(proxy_info)
