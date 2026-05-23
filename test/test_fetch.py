from __future__ import annotations

import gzip
import json
import unittest
from unittest.mock import MagicMock, patch

from qgis.PyQt.QtNetwork import QNetworkRequest

from src import fetch


class TestFetchModule(unittest.TestCase):
    """Test cases for the fetch module."""

    def setUp(self) -> None:
        """Set up test fixtures."""
        self.mock_toc_data = {
            'link': {
                'item': [
                    {
                        'label': 'Test Dataset',
                        'extension': {
                            'id': 'TEST_DATA',
                            'annotation': [
                                {'type': 'UPDATE_DATA', 'date': '2024-01-01'},
                                {
                                    'type': 'UPDATE_STRUCTURE',
                                    'date': '2023-12-01',
                                },
                                {
                                    'type': 'OBS_PERIOD_OVERALL_OLDEST',
                                    'title': '2020',
                                },
                                {
                                    'type': 'OBS_PERIOD_OVERALL_LATEST',
                                    'title': '2024',
                                },
                            ],
                        },
                        'class': 'dataset',
                    }
                ]
            }
        }

    @patch('src.fetch._retry_request')
    def test_get_toc_success(self, mock_retry: MagicMock) -> None:
        """Test successful TOC retrieval."""
        compressed_data = gzip.compress(
            json.dumps(self.mock_toc_data).encode('utf-8')
        )
        mock_retry.return_value = compressed_data

        result = fetch.get_toc(agency='EUROSTAT', lang='en')

        self.assertIsInstance(result, list)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]['code'], 'TEST_DATA')
        self.assertEqual(result[0]['title'], 'Test Dataset')
        self.assertEqual(result[0]['data_start'], '2020')
        self.assertEqual(result[0]['data_end'], '2024')

    @patch('src.fetch._retry_request')
    def test_get_toc_connection_error(self, mock_retry: MagicMock) -> None:
        """Test TOC retrieval with connection error."""
        mock_retry.return_value = None

        with self.assertRaises(ConnectionError):
            fetch.get_toc(agency='EUROSTAT', lang='en')

    @patch('src.fetch._retry_request')
    def test_get_pars_success(self, mock_retry: MagicMock) -> None:
        """Test getting dataset parameters."""
        mock_df_xml = b"""<?xml version="1.0" encoding="UTF-8"?>
        <message:Structure xmlns:message="http://www.sdmx.org/resources/sdmxml/schemas/v2_1/message"
                          xmlns:structure="http://www.sdmx.org/resources/sdmxml/schemas/v2_1/structure">
            <message:Structures>
                <structure:Dataflows>
                    <structure:Dataflow>
                        <structure:Structure>
                            <Ref id="DSD_TEST" />
                        </structure:Structure>
                    </structure:Dataflow>
                </structure:Dataflows>
            </message:Structures>
        </message:Structure>"""

        mock_dsd_xml = b"""<?xml version="1.0" encoding="UTF-8"?>
        <message:Structure xmlns:message="http://www.sdmx.org/resources/sdmxml/schemas/v2_1/message"
                          xmlns:structure="http://www.sdmx.org/resources/sdmxml/schemas/v2_1/structure">
            <message:Structures>
                <structure:DataStructures>
                    <structure:DataStructure>
                        <structure:DataStructureComponents>
                            <structure:DimensionList>
                                <structure:Dimension id="geo">
                                    <structure:LocalRepresentation>
                                        <structure:Enumeration>
                                            <Ref id="CL_GEO" />
                                        </structure:Enumeration>
                                    </structure:LocalRepresentation>
                                </structure:Dimension>
                                <structure:Dimension id="time">
                                    <structure:LocalRepresentation>
                                        <structure:Enumeration>
                                            <Ref id="CL_TIME" />
                                        </structure:Enumeration>
                                    </structure:LocalRepresentation>
                                </structure:Dimension>
                            </structure:DimensionList>
                        </structure:DataStructureComponents>
                    </structure:DataStructure>
                </structure:DataStructures>
            </message:Structures>
        </message:Structure>"""

        mock_retry.side_effect = [mock_df_xml, mock_dsd_xml]

        pars = fetch.get_pars('TEST_DATA')

        self.assertIsInstance(pars, list)
        self.assertEqual(len(pars), 2)
        self.assertIn('geo', pars)
        self.assertIn('time', pars)

    @patch('src.fetch._retry_request')
    def test_get_pars_dataset_not_found(self, mock_retry: MagicMock) -> None:
        """Test get_pars with non-existent dataset."""
        mock_retry.return_value = None

        with self.assertRaises(ValueError):
            fetch.get_pars('NONEXISTENT')

    @patch('src.fetch._retry_request')
    def test_get_dic_success(self, mock_retry: MagicMock) -> None:
        """Test getting dimension dictionary."""
        mock_df_xml = b"""<?xml version="1.0" encoding="UTF-8"?>
        <message:Structure xmlns:message="http://www.sdmx.org/resources/sdmxml/schemas/v2_1/message"
                          xmlns:structure="http://www.sdmx.org/resources/sdmxml/schemas/v2_1/structure">
            <message:Structures>
                <structure:Dataflows>
                    <structure:Dataflow>
                        <structure:Structure>
                            <Ref id="DSD_TEST" />
                        </structure:Structure>
                    </structure:Dataflow>
                </structure:Dataflows>
            </message:Structures>
        </message:Structure>"""

        mock_dsd_xml = b"""<?xml version="1.0" encoding="UTF-8"?>
        <message:Structure xmlns:message="http://www.sdmx.org/resources/sdmxml/schemas/v2_1/message"
                          xmlns:structure="http://www.sdmx.org/resources/sdmxml/schemas/v2_1/structure">
            <message:Structures>
                <structure:DataStructures>
                    <structure:DataStructure>
                        <structure:DataStructureComponents>
                            <structure:DimensionList>
                                <structure:Dimension id="geo">
                                    <structure:LocalRepresentation>
                                        <structure:Enumeration>
                                            <Ref id="CL_GEO" />
                                        </structure:Enumeration>
                                    </structure:LocalRepresentation>
                                </structure:Dimension>
                            </structure:DimensionList>
                        </structure:DataStructureComponents>
                    </structure:DataStructure>
                </structure:DataStructures>
            </message:Structures>
        </message:Structure>"""

        mock_codelist_tsv = gzip.compress(
            b'BE\tBelgium\r\nFR\tFrance\r\nDE\tGermany\r\n'
        )

        mock_retry.side_effect = [mock_df_xml, mock_dsd_xml, mock_codelist_tsv]

        dic = fetch.get_dic('TEST_DATA', par='geo', full=True, lang='en')

        self.assertIsInstance(dic, list)
        self.assertEqual(len(dic), 3)
        self.assertEqual(dic[0], ('BE', 'Belgium'))
        self.assertEqual(dic[1], ('FR', 'France'))

    @patch('src.fetch._retry_request')
    def test_get_dic_invalid_parameter(self, mock_retry: MagicMock) -> None:
        """Test get_dic with invalid parameter name."""
        mock_df_xml = b"""<?xml version="1.0" encoding="UTF-8"?>
        <message:Structure xmlns:message="http://www.sdmx.org/resources/sdmxml/schemas/v2_1/message"
                          xmlns:structure="http://www.sdmx.org/resources/sdmxml/schemas/v2_1/structure">
            <message:Structures>
                <structure:Dataflows>
                    <structure:Dataflow>
                        <structure:Structure>
                            <Ref id="DSD_TEST" />
                        </structure:Structure>
                    </structure:Dataflow>
                </structure:Dataflows>
            </message:Structures>
        </message:Structure>"""

        mock_dsd_xml = b"""<?xml version="1.0" encoding="UTF-8"?>
        <message:Structure xmlns:message="http://www.sdmx.org/resources/sdmxml/schemas/v2_1/message"
                          xmlns:structure="http://www.sdmx.org/resources/sdmxml/schemas/v2_1/structure">
            <message:Structures>
                <structure:DataStructures>
                    <structure:DataStructure>
                        <structure:DataStructureComponents>
                            <structure:DimensionList>
                                <structure:Dimension id="geo">
                                    <structure:LocalRepresentation>
                                        <structure:Enumeration>
                                            <Ref id="CL_GEO" />
                                        </structure:Enumeration>
                                    </structure:LocalRepresentation>
                                </structure:Dimension>
                            </structure:DimensionList>
                        </structure:DataStructureComponents>
                    </structure:DataStructure>
                </structure:DataStructures>
            </message:Structures>
        </message:Structure>"""

        mock_retry.side_effect = [mock_df_xml, mock_dsd_xml]

        with self.assertRaises(ValueError):
            fetch.get_dic(
                'TEST_DATA', par='invalid_param', full=True, lang='en'
            )

    @patch('src.fetch._retry_request')
    def test_get_data_success(self, mock_retry: MagicMock) -> None:
        """Test downloading dataset."""
        mock_df_xml = b"""<?xml version="1.0" encoding="UTF-8"?>
        <message:Structure xmlns:message="http://www.sdmx.org/resources/sdmxml/schemas/v2_1/message"
                          xmlns:structure="http://www.sdmx.org/resources/sdmxml/schemas/v2_1/structure">
            <message:Structures>
                <structure:Dataflows>
                    <structure:Dataflow>
                        <structure:Structure>
                            <Ref id="DSD_TEST" />
                        </structure:Structure>
                    </structure:Dataflow>
                </structure:Dataflows>
            </message:Structures>
        </message:Structure>"""

        mock_dsd_xml = b"""<?xml version="1.0" encoding="UTF-8"?>
        <message:Structure xmlns:message="http://www.sdmx.org/resources/sdmxml/schemas/v2_1/message"
                          xmlns:structure="http://www.sdmx.org/resources/sdmxml/schemas/v2_1/structure">
            <message:Structures>
                <structure:DataStructures>
                    <structure:DataStructure>
                        <structure:DataStructureComponents>
                            <structure:DimensionList>
                                <structure:Dimension id="geo" position="0">
                                    <structure:LocalRepresentation>
                                        <structure:Enumeration>
                                            <Ref id="CL_GEO" />
                                        </structure:Enumeration>
                                    </structure:LocalRepresentation>
                                </structure:Dimension>
                            </structure:DimensionList>
                        </structure:DataStructureComponents>
                    </structure:DataStructure>
                </structure:DataStructures>
            </message:Structures>
        </message:Structure>"""

        mock_tsv_data = gzip.compress(
            b'geo\\time\t2020\t2021\r\nBE\t100\t105\r\nFR\t200\t210\r\n'
        )

        mock_retry.side_effect = [mock_df_xml, mock_dsd_xml, mock_tsv_data]

        result = fetch.get_data('TEST_DATA')

        self.assertIsInstance(result, dict)
        self.assertIn('columns', result)
        self.assertIn('data', result)
        self.assertGreater(len(result['data']), 0)

    @patch('src.fetch._retry_request')
    def test_get_data_with_filters(self, mock_retry: MagicMock) -> None:
        """Test downloading dataset with filters."""
        mock_df_xml = b"""<?xml version="1.0" encoding="UTF-8"?>
        <message:Structure xmlns:message="http://www.sdmx.org/resources/sdmxml/schemas/v2_1/message"
                          xmlns:structure="http://www.sdmx.org/resources/sdmxml/schemas/v2_1/structure">
            <message:Structures>
                <structure:Dataflows>
                    <structure:Dataflow>
                        <structure:Structure>
                            <Ref id="DSD_TEST" />
                        </structure:Structure>
                    </structure:Dataflow>
                </structure:Dataflows>
            </message:Structures>
        </message:Structure>"""

        mock_dsd_xml = b"""<?xml version="1.0" encoding="UTF-8"?>
        <message:Structure xmlns:message="http://www.sdmx.org/resources/sdmxml/schemas/v2_1/message"
                          xmlns:structure="http://www.sdmx.org/resources/sdmxml/schemas/v2_1/structure">
            <message:Structures>
                <structure:DataStructures>
                    <structure:DataStructure>
                        <structure:DataStructureComponents>
                            <structure:DimensionList>
                                <structure:Dimension id="geo" position="0">
                                    <structure:LocalRepresentation>
                                        <structure:Enumeration>
                                            <Ref id="CL_GEO" />
                                        </structure:Enumeration>
                                    </structure:LocalRepresentation>
                                </structure:Dimension>
                            </structure:DimensionList>
                        </structure:DataStructureComponents>
                    </structure:DataStructure>
                </structure:DataStructures>
            </message:Structures>
        </message:Structure>"""

        mock_tsv_data = gzip.compress(
            b'geo\\time\t2022\t2023\r\nBE\t110\t115\r\n'
        )

        mock_retry.side_effect = [mock_df_xml, mock_dsd_xml, mock_tsv_data]

        result = fetch.get_data(
            'TEST_DATA', filter_pars={'startPeriod': 2022, 'endPeriod': 2023}
        )

        self.assertIsInstance(result, dict)
        self.assertIn('columns', result)
        self.assertIn('data', result)

    @patch('src.fetch.QgsNetworkAccessManager')
    def test_blocking_request_success(self, mock_qgs_manager: MagicMock) -> None:
        """Test successful blocking request."""
        mock_manager = MagicMock()
        mock_reply = MagicMock()
        mock_reply.error.return_value = 0
        mock_reply.readAll.return_value.data.return_value = b'test data'

        mock_qgs_manager.instance.return_value = mock_manager
        mock_manager.get.return_value = mock_reply

        data = fetch._blocking_request('http://test.url')

        self.assertEqual(data, b'test data')
        mock_reply.deleteLater.assert_called_once()

    @patch('src.fetch.QgsNetworkAccessManager')
    def test_blocking_request_error(self, mock_qgs_manager: MagicMock) -> None:
        """Test blocking request with network error."""
        mock_manager = MagicMock()
        mock_reply = MagicMock()
        mock_reply.error.return_value = 1

        mock_qgs_manager.instance.return_value = mock_manager
        mock_manager.get.return_value = mock_reply

        data = fetch._blocking_request('http://test.url')

        self.assertIsNone(data)
        mock_reply.deleteLater.assert_called_once()

    @patch('src.fetch._blocking_request')
    def test_retry_request_success_first_attempt(self, mock_blocking: MagicMock) -> None:
        """Test retry succeeds on first attempt."""
        mock_blocking.return_value = b'success'

        data = fetch._retry_request('http://test.url')

        self.assertEqual(data, b'success')
        self.assertEqual(mock_blocking.call_count, 1)

    @patch('src.fetch._blocking_request')
    def test_retry_request_success_after_retries(self, mock_blocking: MagicMock) -> None:
        """Test retry succeeds after multiple attempts."""
        mock_blocking.side_effect = [None, None, b'success']

        data = fetch._retry_request('http://test.url')

        self.assertEqual(data, b'success')
        self.assertEqual(mock_blocking.call_count, 3)

    @patch('src.fetch._blocking_request')
    def test_retry_request_max_attempts_exceeded(self, mock_blocking: MagicMock) -> None:
        """Test retry fails after max attempts."""
        mock_blocking.return_value = None

        data = fetch._retry_request('http://test.url', max_attempts=4)

        self.assertIsNone(data)
        self.assertEqual(mock_blocking.call_count, 4)

    @patch('src.fetch._blocking_request')
    def test_retry_request_server_unavailable(self, mock_blocking: MagicMock) -> None:
        """Test retry with server unavailable error."""
        mock_blocking.return_value = b'https://sorry.ec.europa.eu/'

        with self.assertRaises(ConnectionError) as ctx:
            fetch._retry_request('http://test.url')

        self.assertIn('temporarily unavailable', str(ctx.exception))

    def test_compatibility_functions(self) -> None:
        """Test compatibility functions for eurostat package interface."""
        fetch.set_requests_args(timeout=60, verify=False)
        args = fetch.get_requests_args()
        self.assertEqual(args, {})

        fetch.setproxy({'https': ['user', 'pass', 'http://proxy:8080']})


class TestGetTocFlat(unittest.TestCase):
    """Test cases for the legacy flat TOC parser (`get_toc_flat`)."""

    def setUp(self) -> None:
        """Build a synthetic JSON TOC payload like the SDMX dataflow endpoint."""
        self.mock_toc_data = {
            'link': {
                'item': [
                    {
                        'label': 'Population by region',
                        'class': 'dataset',
                        'extension': {
                            'id': 'POP_REG',
                            'annotation': [
                                {'type': 'UPDATE_DATA', 'date': '2024-03-15'},
                                {
                                    'type': 'UPDATE_STRUCTURE',
                                    'date': '2023-11-02',
                                },
                                {
                                    'type': 'OBS_PERIOD_OVERALL_OLDEST',
                                    'title': '2000',
                                },
                                {
                                    'type': 'OBS_PERIOD_OVERALL_LATEST',
                                    'title': '2023',
                                },
                            ],
                        },
                    },
                    {
                        'label': 'GDP by region',
                        'class': 'dataset',
                        'extension': {
                            'id': 'GDP_REG',
                            'annotation': [
                                {'type': 'UPDATE_DATA', 'date': '2024-02-01'},
                                {
                                    'type': 'UPDATE_STRUCTURE',
                                    'date': '2023-10-01',
                                },
                                {
                                    'type': 'OBS_PERIOD_OVERALL_OLDEST',
                                    'title': '1995',
                                },
                                {
                                    'type': 'OBS_PERIOD_OVERALL_LATEST',
                                    'title': '2022',
                                },
                            ],
                        },
                    },
                ]
            }
        }

    @patch('src.fetch._retry_request')
    def test_get_toc_flat_success(self, mock_retry: MagicMock) -> None:
        """Returns a flat list of dicts with the legacy 7-field shape."""
        mock_retry.return_value = gzip.compress(
            json.dumps(self.mock_toc_data).encode('utf-8')
        )

        result = fetch.get_toc_flat(agency='EUROSTAT', lang='en')

        self.assertIsInstance(result, list)
        self.assertEqual(len(result), 2)

        first = result[0]
        # Legacy shape: no 'level' / 'values' fields.
        expected_keys = {
            'title',
            'code',
            'type',
            'last_update_of_data',
            'last_table_structure_change',
            'data_start',
            'data_end',
        }
        self.assertEqual(set(first.keys()), expected_keys)
        self.assertEqual(first['code'], 'POP_REG')
        self.assertEqual(first['title'], 'Population by region')
        self.assertEqual(first['type'], 'dataset')
        self.assertEqual(first['last_update_of_data'], '2024-03-15')
        self.assertEqual(first['last_table_structure_change'], '2023-11-02')
        self.assertEqual(first['data_start'], '2000')
        self.assertEqual(first['data_end'], '2023')

    @patch('src.fetch._retry_request')
    def test_get_toc_flat_multiple_items(self, mock_retry: MagicMock) -> None:
        """Every item from the payload is preserved in order."""
        mock_retry.return_value = gzip.compress(
            json.dumps(self.mock_toc_data).encode('utf-8')
        )

        result = fetch.get_toc_flat(agency='EUROSTAT', lang='en')

        codes = [row['code'] for row in result]
        self.assertEqual(codes, ['POP_REG', 'GDP_REG'])
        self.assertEqual(result[1]['data_start'], '1995')
        self.assertEqual(result[1]['data_end'], '2022')

    @patch('src.fetch._retry_request')
    def test_get_toc_flat_connection_error(self, mock_retry: MagicMock) -> None:
        """`None` from the network layer surfaces as ConnectionError."""
        mock_retry.return_value = None

        with self.assertRaises(ConnectionError):
            fetch.get_toc_flat(agency='EUROSTAT', lang='en')

    @patch('src.fetch._retry_request')
    def test_get_toc_flat_missing_annotations(self, mock_retry: MagicMock) -> None:
        """Annotations are optional fields; missing ones stay as None."""
        sparse_payload = {
            'link': {
                'item': [
                    {
                        'label': 'Minimal dataset',
                        'class': 'dataset',
                        'extension': {
                            'id': 'MIN_DS',
                            'annotation': [],
                        },
                    }
                ]
            }
        }
        mock_retry.return_value = gzip.compress(
            json.dumps(sparse_payload).encode('utf-8')
        )

        result = fetch.get_toc_flat(agency='EUROSTAT', lang='en')

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]['code'], 'MIN_DS')
        self.assertIsNone(result[0]['last_update_of_data'])
        self.assertIsNone(result[0]['last_table_structure_change'])
        self.assertIsNone(result[0]['data_start'])
        self.assertIsNone(result[0]['data_end'])

    @patch('src.fetch._retry_request')
    def test_get_toc_flat_uses_agency_base_url(self, mock_retry: MagicMock) -> None:
        """The agency parameter selects the matching BASE_URL entry."""
        mock_retry.return_value = gzip.compress(
            json.dumps({'link': {'item': []}}).encode('utf-8')
        )

        fetch.get_toc_flat(agency='COMP', lang='fr')

        self.assertEqual(mock_retry.call_count, 1)
        called_url = mock_retry.call_args[0][0]
        self.assertTrue(called_url.startswith(fetch.BASE_URL['COMP']))
        self.assertIn('lang=fr', called_url)
        self.assertIn('format=JSON', called_url)


class TestGiscoRequestBlocking(unittest.TestCase):
    """Test cases for the GISCO synchronous wrapper."""

    @patch('src.settings.GLOBAL_SETTINGS')
    def test_gisco_request_blocking_returns_payload_bytes(
        self, mock_global_settings: MagicMock
    ) -> None:
        """Returns the raw bytes from response.content().data()."""
        payload = b'{"type":"FeatureCollection","features":[]}'
        mock_response = MagicMock()
        mock_response.content.return_value.data.return_value = payload
        mock_global_settings.network_manager.blockingGet.return_value = (
            mock_response
        )

        result = fetch.gisco_request_blocking(
            'https://gisco-services.ec.europa.eu/distribution/v2/test.geojson'
        )

        self.assertEqual(result, payload)

    @patch('src.settings.GLOBAL_SETTINGS')
    def test_gisco_request_blocking_calls_blocking_get_once(
        self, mock_global_settings: MagicMock
    ) -> None:
        """blockingGet is called exactly once with a QNetworkRequest."""
        mock_response = MagicMock()
        mock_response.content.return_value.data.return_value = b'ok'
        mock_global_settings.network_manager.blockingGet.return_value = (
            mock_response
        )

        fetch.gisco_request_blocking('https://example.test/file')

        mock_global_settings.network_manager.blockingGet.assert_called_once()
        sent_request = (
            mock_global_settings.network_manager.blockingGet.call_args[0][0]
        )
        self.assertIsInstance(sent_request, QNetworkRequest)
        self.assertEqual(
            sent_request.url().toString(), 'https://example.test/file'
        )

    @patch('src.settings.GLOBAL_SETTINGS')
    def test_gisco_request_blocking_empty_body(self, mock_global_settings: MagicMock) -> None:
        """An empty response body still returns bytes (no crash)."""
        mock_response = MagicMock()
        mock_response.content.return_value.data.return_value = b''
        mock_global_settings.network_manager.blockingGet.return_value = (
            mock_response
        )

        result = fetch.gisco_request_blocking('https://example.test/empty')

        self.assertEqual(result, b'')

    @patch('src.settings.GLOBAL_SETTINGS')
    def test_gisco_request_blocking_propagates_manager_exception(
        self, mock_global_settings: MagicMock
    ) -> None:
        """If the QGIS manager raises, the exception bubbles up.

        `gisco_request_blocking` has no try/except — failures from the
        network layer must surface to the caller rather than be swallowed.
        """
        mock_global_settings.network_manager.blockingGet.side_effect = (
            RuntimeError('network down')
        )

        with self.assertRaises(RuntimeError):
            fetch.gisco_request_blocking('https://example.test/boom')


class TestGiscoRequest(unittest.TestCase):
    """Test cases for the GISCO async wrapper."""

    @patch('src.settings.GLOBAL_SETTINGS')
    def test_gisco_request_returns_manager_reply(self, mock_global_settings: MagicMock) -> None:
        """The QNetworkReply returned by manager.get() is passed through."""
        mock_reply = MagicMock(name='QNetworkReply')
        mock_global_settings.network_manager.get.return_value = mock_reply

        result = fetch.gisco_request('https://example.test/async')

        self.assertIs(result, mock_reply)

    @patch('src.settings.GLOBAL_SETTINGS')
    def test_gisco_request_uses_default_manager(self, mock_global_settings: MagicMock) -> None:
        """When no manager is provided, GLOBAL_SETTINGS.network_manager is used."""
        mock_global_settings.network_manager.get.return_value = MagicMock()

        fetch.gisco_request('https://example.test/default')

        mock_global_settings.network_manager.get.assert_called_once()
        sent_request = (
            mock_global_settings.network_manager.get.call_args[0][0]
        )
        self.assertIsInstance(sent_request, QNetworkRequest)
        self.assertEqual(
            sent_request.url().toString(), 'https://example.test/default'
        )

    @patch('src.settings.GLOBAL_SETTINGS')
    def test_gisco_request_uses_custom_manager(self, mock_global_settings: MagicMock) -> None:
        """A caller-supplied manager bypasses GLOBAL_SETTINGS entirely."""
        custom_manager = MagicMock(name='CustomManager')
        custom_reply = MagicMock(name='CustomReply')
        custom_manager.get.return_value = custom_reply

        result = fetch.gisco_request(
            'https://example.test/custom', manager=custom_manager
        )

        self.assertIs(result, custom_reply)
        custom_manager.get.assert_called_once()
        mock_global_settings.network_manager.get.assert_not_called()

    @patch('src.settings.GLOBAL_SETTINGS')
    def test_gisco_request_propagates_manager_exception(
        self, mock_global_settings: MagicMock
    ) -> None:
        """`gisco_request` has no error handling; exceptions bubble up."""
        mock_global_settings.network_manager.get.side_effect = RuntimeError(
            'manager unavailable'
        )

        with self.assertRaises(RuntimeError):
            fetch.gisco_request('https://example.test/boom')


if __name__ == '__main__':
    unittest.main()
