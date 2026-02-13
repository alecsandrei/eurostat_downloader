from __future__ import annotations

import gzip
import json
import unittest
from unittest.mock import MagicMock, patch

from src import fetch


class TestFetchModule(unittest.TestCase):
    """Test cases for the fetch module."""

    def setUp(self):
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
    def test_get_toc_success(self, mock_retry):
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
        self.assertEqual(result[0]['data start'], '2020')
        self.assertEqual(result[0]['data end'], '2024')

    @patch('src.fetch._retry_request')
    def test_get_toc_connection_error(self, mock_retry):
        """Test TOC retrieval with connection error."""
        mock_retry.return_value = None

        with self.assertRaises(ConnectionError):
            fetch.get_toc(agency='EUROSTAT', lang='en')

    @patch('src.fetch._retry_request')
    def test_get_pars_success(self, mock_retry):
        """Test getting dataset parameters."""
        mock_df_xml = b'''<?xml version="1.0" encoding="UTF-8"?>
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
        </message:Structure>'''

        mock_dsd_xml = b'''<?xml version="1.0" encoding="UTF-8"?>
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
        </message:Structure>'''

        mock_retry.side_effect = [mock_df_xml, mock_dsd_xml]

        pars = fetch.get_pars('TEST_DATA')

        self.assertIsInstance(pars, list)
        self.assertEqual(len(pars), 2)
        self.assertIn('geo', pars)
        self.assertIn('time', pars)

    @patch('src.fetch._retry_request')
    def test_get_pars_dataset_not_found(self, mock_retry):
        """Test get_pars with non-existent dataset."""
        mock_retry.return_value = None

        with self.assertRaises(ValueError):
            fetch.get_pars('NONEXISTENT')

    @patch('src.fetch._retry_request')
    def test_get_dic_success(self, mock_retry):
        """Test getting dimension dictionary."""
        mock_df_xml = b'''<?xml version="1.0" encoding="UTF-8"?>
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
        </message:Structure>'''

        mock_dsd_xml = b'''<?xml version="1.0" encoding="UTF-8"?>
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
        </message:Structure>'''

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
    def test_get_dic_invalid_parameter(self, mock_retry):
        """Test get_dic with invalid parameter name."""
        mock_df_xml = b'''<?xml version="1.0" encoding="UTF-8"?>
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
        </message:Structure>'''

        mock_dsd_xml = b'''<?xml version="1.0" encoding="UTF-8"?>
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
        </message:Structure>'''

        mock_retry.side_effect = [mock_df_xml, mock_dsd_xml]

        with self.assertRaises(ValueError):
            fetch.get_dic('TEST_DATA', par='invalid_param', full=True, lang='en')

    @patch('src.fetch._retry_request')
    def test_get_data_success(self, mock_retry):
        """Test downloading dataset."""
        mock_df_xml = b'''<?xml version="1.0" encoding="UTF-8"?>
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
        </message:Structure>'''

        mock_dsd_xml = b'''<?xml version="1.0" encoding="UTF-8"?>
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
        </message:Structure>'''

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
    def test_get_data_with_filters(self, mock_retry):
        """Test downloading dataset with filters."""
        mock_df_xml = b'''<?xml version="1.0" encoding="UTF-8"?>
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
        </message:Structure>'''

        mock_dsd_xml = b'''<?xml version="1.0" encoding="UTF-8"?>
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
        </message:Structure>'''

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
    def test_blocking_request_success(self, mock_qgs_manager):
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
    def test_blocking_request_error(self, mock_qgs_manager):
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
    def test_retry_request_success_first_attempt(self, mock_blocking):
        """Test retry succeeds on first attempt."""
        mock_blocking.return_value = b'success'

        data = fetch._retry_request('http://test.url')

        self.assertEqual(data, b'success')
        self.assertEqual(mock_blocking.call_count, 1)

    @patch('src.fetch._blocking_request')
    def test_retry_request_success_after_retries(self, mock_blocking):
        """Test retry succeeds after multiple attempts."""
        mock_blocking.side_effect = [None, None, b'success']

        data = fetch._retry_request('http://test.url')

        self.assertEqual(data, b'success')
        self.assertEqual(mock_blocking.call_count, 3)

    @patch('src.fetch._blocking_request')
    def test_retry_request_max_attempts_exceeded(self, mock_blocking):
        """Test retry fails after max attempts."""
        mock_blocking.return_value = None

        data = fetch._retry_request('http://test.url', max_attempts=4)

        self.assertIsNone(data)
        self.assertEqual(mock_blocking.call_count, 4)

    @patch('src.fetch._blocking_request')
    def test_retry_request_server_unavailable(self, mock_blocking):
        """Test retry with server unavailable error."""
        mock_blocking.return_value = b'https://sorry.ec.europa.eu/'

        with self.assertRaises(ConnectionError) as ctx:
            fetch._retry_request('http://test.url')

        self.assertIn('temporarily unavailable', str(ctx.exception))

    def test_compatibility_functions(self):
        """Test compatibility functions for eurostat package interface."""
        fetch.set_requests_args(timeout=60, verify=False)
        args = fetch.get_requests_args()
        self.assertEqual(args, {})

        fetch.setproxy({'https': ['user', 'pass', 'http://proxy:8080']})


if __name__ == '__main__':
    unittest.main()
