# coding=utf-8
"""Tests for settings module - ProxySettings, GlobalSettings."""

__author__ = 'cuvuliucalexandrei@gmail.com'
__date__ = '2024-01-30'

import unittest
from unittest.mock import Mock, patch
from qgis.core import QgsSettings, QgsNetworkAccessManager

from eurostat_downloader.src.settings import ProxySettings, GlobalSettings, _get_qgis_proxy
from eurostat_downloader.src.enums import Agency
from test.utilities import get_qgis_app

QGIS_APP = get_qgis_app()


class TestProxySettings(unittest.TestCase):
    """Test ProxySettings named tuple."""

    def test_proxy_settings_creation(self):
        """Test creating ProxySettings."""
        proxy = ProxySettings(
            host='proxy.example.com',
            port='8080',
            user='testuser',
            password='testpass',
        )

        self.assertEqual(proxy.host, 'proxy.example.com')
        self.assertEqual(proxy.port, '8080')
        self.assertEqual(proxy.user, 'testuser')
        self.assertEqual(proxy.password, 'testpass')

    def test_proxy_settings_without_auth(self):
        """Test creating ProxySettings without authentication."""
        proxy = ProxySettings(
            host='proxy.example.com', port='8080', user=None, password=None
        )

        self.assertEqual(proxy.host, 'proxy.example.com')
        self.assertEqual(proxy.port, '8080')
        self.assertIsNone(proxy.user)
        self.assertIsNone(proxy.password)


class TestGetQGISProxy(unittest.TestCase):
    """Test _get_qgis_proxy function."""

    def setUp(self):
        """Setup test fixtures."""
        self.mock_settings = Mock(spec=QgsSettings)

    @patch('eurostat_downloader.src.settings.QGS_SETTINGS')
    def test_proxy_disabled(self, mock_qgs_settings):
        """Test when proxy is disabled."""
        mock_qgs_settings.value.side_effect = lambda key, default, type: {
            'proxy/proxyEnabled': 'false',
        }.get(key, default)

        result = _get_qgis_proxy()

        self.assertIsNone(result)

    @patch('eurostat_downloader.src.settings.QGS_SETTINGS')
    def test_http_proxy_enabled(self, mock_qgs_settings):
        """Test when HTTP proxy is enabled."""

        def settings_value(key, default='', type=str):
            values = {
                'proxy/proxyEnabled': 'true',
                'proxy/proxyType': 'HttpProxy',
                'proxy/proxyHost': 'proxy.example.com',
                'proxy/proxyPort': '8080',
                'proxy/proxyUser': 'user',
                'proxy/proxyPassword': 'pass',
            }
            return values.get(key, default)

        mock_qgs_settings.value.side_effect = settings_value

        result = _get_qgis_proxy()

        self.assertIsNotNone(result)
        self.assertEqual(result.host, 'proxy.example.com')
        self.assertEqual(result.port, '8080')
        self.assertEqual(result.user, 'user')
        self.assertEqual(result.password, 'pass')

    @patch('eurostat_downloader.src.settings.QGS_SETTINGS')
    def test_socks5_proxy_enabled(self, mock_qgs_settings):
        """Test when SOCKS5 proxy is enabled."""

        def settings_value(key, default='', type=str):
            values = {
                'proxy/proxyEnabled': 'true',
                'proxy/proxyType': 'Socks5Proxy',
                'proxy/proxyHost': 'socks.example.com',
                'proxy/proxyPort': '1080',
                'proxy/proxyUser': '',
                'proxy/proxyPassword': '',
            }
            return values.get(key, default)

        mock_qgs_settings.value.side_effect = settings_value

        result = _get_qgis_proxy()

        self.assertIsNotNone(result)
        self.assertEqual(result.host, 'socks.example.com')
        self.assertEqual(result.port, '1080')

    @patch('eurostat_downloader.src.settings.QGS_SETTINGS')
    def test_http_caching_proxy_enabled(self, mock_qgs_settings):
        """HttpCachingProxy is in the accepted-types list and must return a
        ProxySettings instance just like HttpProxy / Socks5Proxy.

        Regression guard: if the accepted-types list in ``_get_qgis_proxy``
        is ever pruned without thought, users on a QGIS install configured
        with an HttpCachingProxy would silently fall through to ``None``
        (no proxy) instead of having their proxy honoured.
        """

        def settings_value(key, default='', type=str):
            values = {
                'proxy/proxyEnabled': 'true',
                'proxy/proxyType': 'HttpCachingProxy',
                'proxy/proxyHost': 'cache.example.com',
                'proxy/proxyPort': '3128',
                'proxy/proxyUser': '',
                'proxy/proxyPassword': '',
            }
            return values.get(key, default)

        mock_qgs_settings.value.side_effect = settings_value

        result = _get_qgis_proxy()

        self.assertIsNotNone(result)
        self.assertEqual(result.host, 'cache.example.com')
        self.assertEqual(result.port, '3128')

    @patch('eurostat_downloader.src.settings.QGS_SETTINGS')
    def test_unknown_proxy_type_returns_none(self, mock_qgs_settings):
        """Proxy enabled with an unrecognised proxy type returns ``None``.

        ``_get_qgis_proxy`` only honours a small set of proxy types
        (Default/Socks5/Http/HttpCaching). Anything else -- e.g. an
        ``FtpCachingProxy`` value or an empty string -- must yield ``None``
        so the caller doesn't construct a half-populated ProxySettings.
        """

        def settings_value(key, default='', type=str):
            values = {
                'proxy/proxyEnabled': 'true',
                'proxy/proxyType': 'FtpCachingProxy',
                'proxy/proxyHost': 'ftp.example.com',
                'proxy/proxyPort': '21',
                'proxy/proxyUser': '',
                'proxy/proxyPassword': '',
            }
            return values.get(key, default)

        mock_qgs_settings.value.side_effect = settings_value

        result = _get_qgis_proxy()

        self.assertIsNone(result)

    @patch('eurostat_downloader.src.settings.QGS_SETTINGS')
    def test_proxy_enabled_empty_string_returns_none(self, mock_qgs_settings):
        """When ``proxy/proxyEnabled`` is the empty string (key unset in
        QgsSettings), ``_get_qgis_proxy`` must return ``None``.

        The check is ``proxy_enabled == 'true'`` -- any other value (the
        default empty string, ``'false'``, or anything truthy-but-not-'true')
        means "no proxy". This test pins the default-unset path explicitly.
        """

        def settings_value(key, default='', type=str):
            # Every key returns its default ''.
            return default

        mock_qgs_settings.value.side_effect = settings_value

        result = _get_qgis_proxy()

        self.assertIsNone(result)

    @patch('eurostat_downloader.src.settings.QGS_SETTINGS')
    @patch('eurostat_downloader.src.settings.QgsNetworkAccessManager')
    def test_default_proxy(self, mock_network_manager, mock_qgs_settings):
        """Test when using default proxy."""

        def settings_value(key, default='', type=str):
            values = {
                'proxy/proxyEnabled': 'true',
                'proxy/proxyType': 'DefaultProxy',
                'proxy/proxyHost': '',
                'proxy/proxyPort': '',
                'proxy/proxyUser': '',
                'proxy/proxyPassword': '',
            }
            return values.get(key, default)

        mock_qgs_settings.value.side_effect = settings_value

        # Mock network manager proxy
        mock_proxy = Mock()
        mock_proxy.hostName.return_value = 'default.proxy.com'
        mock_proxy.port.return_value = 3128
        mock_proxy.user.return_value = 'default_user'
        mock_proxy.password.return_value = 'default_pass'

        mock_instance = Mock()
        mock_instance.proxy.return_value.applicationProxy.return_value = (
            mock_proxy
        )
        mock_network_manager.instance.return_value = mock_instance

        result = _get_qgis_proxy()

        self.assertIsNotNone(result)
        self.assertEqual(result.host, 'default.proxy.com')
        self.assertEqual(result.port, '3128')


class TestGlobalSettings(unittest.TestCase):
    """Test GlobalSettings dataclass."""

    def setUp(self):
        """Setup test fixtures."""
        self.qgs_settings = QgsSettings()

    def test_global_settings_initialization(self):
        """Test GlobalSettings initializes with defaults."""
        settings = GlobalSettings(qgs_settings=self.qgs_settings)

        self.assertEqual(settings.qgs_settings, self.qgs_settings)
        self.assertIsInstance(settings.agencies, list)
        self.assertEqual(len(settings.agencies), len(Agency))
        self.assertTrue(settings.verify_ssl)
        self.assertIsInstance(settings.network_manager, QgsNetworkAccessManager)

    def test_global_settings_agencies(self):
        """Test all agencies are included."""
        settings = GlobalSettings(qgs_settings=self.qgs_settings)

        for agency in Agency:
            self.assertIn(agency, settings.agencies)

    @patch('eurostat_downloader.src.settings._get_qgis_proxy')
    def test_global_settings_with_proxy(self, mock_get_proxy):
        """Test GlobalSettings with proxy configuration."""
        mock_proxy = ProxySettings(
            host='test.proxy.com', port='8080', user='user', password='pass'
        )
        mock_get_proxy.return_value = mock_proxy

        settings = GlobalSettings(qgs_settings=self.qgs_settings)

        self.assertEqual(settings.proxy, mock_proxy)

    @patch('eurostat_downloader.src.settings._get_qgis_proxy')
    def test_global_settings_without_proxy(self, mock_get_proxy):
        """Test GlobalSettings without proxy."""
        mock_get_proxy.return_value = None

        settings = GlobalSettings(qgs_settings=self.qgs_settings)

        self.assertIsNone(settings.proxy)

    def test_verify_ssl_default(self):
        """Test verify_ssl defaults to True."""
        settings = GlobalSettings(qgs_settings=self.qgs_settings)

        self.assertTrue(settings.verify_ssl)


if __name__ == '__main__':
    suite = unittest.TestLoader().loadTestsFromModule(__import__(__name__))
    runner = unittest.TextTestRunner(verbosity=2)
    runner.run(suite)
