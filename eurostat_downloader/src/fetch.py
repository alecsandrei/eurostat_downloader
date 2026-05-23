from __future__ import annotations

import gzip
import json
import os
import xml.etree.ElementTree as ET
from itertools import product
from typing import cast

from qgis.core import QgsNetworkAccessManager
from qgis.PyQt.QtCore import QEventLoop, QUrl
from qgis.PyQt.QtNetwork import QNetworkReply, QNetworkRequest

DimsResult = (
    list[str | None]
    | list[tuple[str | None, str | None]]
    | list[tuple[str | None, str | None, str | None]]
)

TocRow = dict[str, str | int | None]

DataValue = str | float | None

DEBUG = os.getenv('EUROSTAT_PLUGIN_DEBUG', '0') == '1'


def _debug(msg: str, prefix: str = '🔍') -> None:
    """Print debug message if DEBUG mode is enabled."""
    if DEBUG:
        print(f'{prefix} [EUROSTAT-FETCH] {msg}')


BASE_URL = {
    'EUROSTAT': 'https://ec.europa.eu/eurostat/api/dissemination/sdmx/2.1/',
    'COMEXT': 'https://ec.europa.eu/eurostat/api/comext/dissemination/sdmx/2.1/',
    'COMP': 'https://webgate.ec.europa.eu/comp/redisstat/api/dissemination/sdmx/2.1/',
    'EMPL': 'https://webgate.ec.europa.eu/empl/redisstat/api/dissemination/sdmx/2.1/',
    'GROW': 'https://webgate.ec.europa.eu/grow/redisstat/api/dissemination/sdmx/2.1/',
}

BASE_ASYNC_URL = {
    'EUROSTAT': 'https://ec.europa.eu/eurostat/api/dissemination/1.0/async/',
    'COMEXT': 'https://ec.europa.eu/eurostat/api/comext/dissemination/1.0/async/',
    'COMP': 'https://ec.europa.eu/eurostat/api/compl/dissemination/1.0/async/',
    'EMPL': 'https://ec.europa.eu/eurostat/api/empl/dissemination/1.0/async/',
    'GROW': 'https://ec.europa.eu/eurostat/api/grow/dissemination/1.0/async/',
}

AGENCY_BY_PROVIDER = [
    ('EUROSTAT', 'ESTAT'),
    ('COMEXT', 'ESTAT'),
    ('COMP', 'COMP'),
    ('EMPL', 'EMPL'),
    ('GROW', 'GROW'),
]

XMLSNS_M = '{http://www.sdmx.org/resources/sdmxml/schemas/v2_1/message}'
XMLSNS_S = '{http://www.sdmx.org/resources/sdmxml/schemas/v2_1/structure}'
XMLSNS_C = '{http://www.sdmx.org/resources/sdmxml/schemas/v2_1/common}'
XMLSNS_L = '{http://www.w3.org/XML/1998/namespace}lang'
XMLSNS_ENV = '{http://schemas.xmlsoap.org/soap/envelope/}'
XMLSNS_ASYNC_NS0 = '{http://estat.ec.europa.eu/disschain/soap/asynchronous}'
XMLSNS_ASYNC_NS1 = '{http://estat.ec.europa.eu/disschain/asynchronous}'
XMLSNS_SYNC_NS0 = '{http://estat.ec.europa.eu/disschain/soap/extraction}'

dim_path = (
    XMLSNS_M
    + 'Structures/'
    + XMLSNS_S
    + 'DataStructures/'
    + XMLSNS_S
    + 'DataStructure/'
    + XMLSNS_S
    + 'DataStructureComponents/'
    + XMLSNS_S
    + 'DimensionList/'
    + XMLSNS_S
    + 'Dimension'
)
dsd_path = (
    XMLSNS_M
    + 'Structures/'
    + XMLSNS_S
    + 'Dataflows/'
    + XMLSNS_S
    + 'Dataflow/'
    + XMLSNS_S
    + 'Structure/Ref'
)
ref_path = XMLSNS_S + 'LocalRepresentation/' + XMLSNS_S + 'Enumeration/Ref'
codelist_path = (
    XMLSNS_M + 'Structures/' + XMLSNS_S + 'Codelists/' + XMLSNS_S + 'Codelist'
)
par_path = (
    XMLSNS_M
    + 'Structures/'
    + XMLSNS_S
    + 'Constraints/'
    + XMLSNS_S
    + 'ContentConstraint/'
    + XMLSNS_S
    + 'CubeRegion/'
    + XMLSNS_C
    + 'KeyValue'
)
val_path = XMLSNS_C + 'Value'
async_key_path = (
    XMLSNS_ENV
    + 'Body/'
    + XMLSNS_ASYNC_NS0
    + 'asyncResponse/'
    + XMLSNS_ASYNC_NS1
    + 'status/'
    + XMLSNS_ASYNC_NS1
    + 'key'
)
async_status_path = (
    XMLSNS_ENV
    + 'Body/'
    + XMLSNS_ASYNC_NS0
    + 'asyncResponse/'
    + XMLSNS_ASYNC_NS1
    + 'status/'
    + XMLSNS_ASYNC_NS1
    + 'status'
)
sync_key_path = (
    XMLSNS_ENV + 'Body/' + XMLSNS_SYNC_NS0 + 'syncResponse/queued/id'
)
sync_status_path = (
    XMLSNS_ENV + 'Body/' + XMLSNS_SYNC_NS0 + 'syncResponse/queued/status'
)


def _blocking_request(url: str, timeout: int = 120000) -> bytes | None:
    """Perform a blocking HTTP GET request using QGIS network manager."""
    manager = QgsNetworkAccessManager.instance()
    request = QNetworkRequest(QUrl(url))

    loop = QEventLoop()
    reply = manager.get(request)
    reply.finished.connect(loop.quit)
    loop.exec()

    if reply.error() == QNetworkReply.NetworkError.NoError:
        # QGIS PyQt stubs return Any from readAll().data(); cast to bytes
        data = cast(bytes, reply.readAll().data())
        reply.deleteLater()
        return data
    else:
        reply.deleteLater()
        return None


def _retry_request(url: str, max_attempts: int = 4) -> bytes | None:
    """Retry a request up to max_attempts times."""
    _debug(f'Starting retry request (max_attempts={max_attempts})')
    for attempt in range(max_attempts):
        if attempt > 0:
            _debug(f'Retry attempt {attempt + 1}/{max_attempts}', '⏱')
        data = _blocking_request(url)
        if data is not None:
            if b'https://sorry.ec.europa.eu/' in data:
                _debug('Server temporarily unavailable', '❌')
                raise ConnectionError('Server temporarily unavailable')
            _debug(f'Success on attempt {attempt + 1}', '✓')
            return data
    _debug(f'All {max_attempts} attempts failed', '❌')
    return None


def get_toc(agency: str = 'EUROSTAT', lang: str = 'en') -> list[TocRow]:
    """Download table of contents as hierarchical tree structure.

    For EUROSTAT, uses the text-based TOC with hierarchy.
    For other agencies, falls back to SDMX dataflow endpoint and infers hierarchy.
    """
    _debug(f'Fetching hierarchical TOC for agency={agency}, lang={lang}', '📋')

    # EUROSTAT has a special text-based TOC endpoint with hierarchy
    if agency == 'EUROSTAT':
        url = (
            'https://ec.europa.eu/eurostat/api/dissemination/catalogue/toc/txt'
        )
        if lang != 'en':
            url += f'?lang={lang}'

        data = _retry_request(url)
        if data is None:
            _debug('Failed to fetch TOC', '❌')
            raise ConnectionError(f'Failed to fetch TOC for {agency}')

        resp_txt = data.decode('utf-8')
        lines = resp_txt.strip().split('\n')

        # Skip header line
        if not lines:
            return []
        lines = lines[1:]

        rows: list[TocRow] = []
        for line in lines:
            parts = line.split('\t')
            if len(parts) < 3:
                continue

            # Count leading spaces BEFORE stripping quotes
            # The format is: "    Title" where spaces are INSIDE the quotes
            title_raw = parts[0]
            # Remove quotes first to expose the spaces
            title_unquoted = title_raw.strip('"')
            # Now count the leading spaces
            indent_count = len(title_unquoted) - len(title_unquoted.lstrip())
            level = indent_count // 4  # 4 spaces per level

            # Clean title and other fields
            title = title_unquoted.lstrip()
            code = parts[1].strip('"')
            _type = parts[2].strip('"')

            # Extract other fields if available
            last_update = (
                parts[3].strip('"').strip() if len(parts) > 3 else None
            )
            last_struct_change = (
                parts[4].strip('"').strip() if len(parts) > 4 else None
            )
            data_start = parts[5].strip('"').strip() if len(parts) > 5 else None
            data_end = parts[6].strip('"').strip() if len(parts) > 6 else None
            values = parts[7].strip('"').strip() if len(parts) > 7 else None

            row: TocRow = {
                'title': title,
                'code': code,
                'type': _type,
                'level': level,
                'last_update_of_data': last_update or '',
                'last_table_structure_change': last_struct_change or '',
                'data_start': data_start or '',
                'data_end': data_end or '',
                'values': values or '',
            }
            rows.append(row)

        _debug(f'Found {len(rows)} items in hierarchy', '✓')
        return rows

    else:
        # Other agencies: use SDMX dataflow endpoint (flat structure)
        # We'll mark everything as level 0 since we can't infer hierarchy
        _debug(
            f'Using SDMX dataflow endpoint for {agency} (no hierarchy available)',
            '⚠',
        )
        base_url = BASE_URL[agency]
        url = f'{base_url}dataflow/all?format=JSON&compressed=true&lang={lang}'

        data = _retry_request(url)
        if data is None:
            _debug('Failed to fetch TOC', '❌')
            raise ConnectionError(f'Failed to fetch TOC for {agency}')

        _debug('Decompressing gzip response...')
        resp_txt = gzip.decompress(data).decode('utf-8')
        resp_dict = json.loads(resp_txt)
        items = resp_dict.get('link', {}).get('item', [])
        _debug(f'Found {len(items)} items', '✓')

        rows = []
        for el in items:
            title = el.get('label', '')
            code = el.get('extension', {}).get('id', '')
            _type = el.get('class', 'dataset')

            # Extract metadata
            last_update = None
            last_struct_change = None
            data_start = None
            data_end = None

            for a in el.get('extension', {}).get('annotation', []):
                if a.get('type') == 'UPDATE_DATA':
                    last_update = a.get('date')
                elif a.get('type') == 'UPDATE_STRUCTURE':
                    last_struct_change = a.get('date')
                elif a.get('type') == 'OBS_PERIOD_OVERALL_OLDEST':
                    data_start = a.get('title')
                elif a.get('type') == 'OBS_PERIOD_OVERALL_LATEST':
                    data_end = a.get('title')

            flat_row: TocRow = {
                'title': title,
                'code': code,
                'type': _type,
                'level': 0,  # Flat structure - all items at root level
                'last_update_of_data': last_update or '',
                'last_table_structure_change': last_struct_change or '',
                'data_start': data_start or '',
                'data_end': data_end or '',
                'values': '',
            }
            rows.append(flat_row)

        _debug(f'Converted to {len(rows)} flat items', '✓')
        return rows


def get_toc_flat(
    agency: str = 'EUROSTAT', lang: str = 'en'
) -> list[TocRow]:
    """Download Eurostat table of contents as flat list (legacy function)."""
    _debug(f'Fetching flat TOC for agency={agency}, lang={lang}', '📋')
    base_url = BASE_URL[agency]
    url = f'{base_url}dataflow/all?format=JSON&compressed=true&lang={lang}'

    data = _retry_request(url)
    if data is None:
        _debug('Failed to fetch TOC', '❌')
        raise ConnectionError(f'Failed to fetch TOC for {agency}')

    _debug('Decompressing gzip response...')
    resp_txt = gzip.decompress(data).decode('utf-8')
    resp_dict = json.loads(resp_txt)
    _debug(f'Found {len(resp_dict["link"]["item"])} items', '✓')

    rows: list[TocRow] = []
    for el in resp_dict['link']['item']:
        title = el['label']
        code = el['extension']['id']
        _type = el['class']
        last_update = None
        last_struct_change = None
        data_start = None
        data_end = None

        for a in el['extension']['annotation']:
            if a['type'] == 'UPDATE_DATA':
                last_update = a['date']
            elif a['type'] == 'UPDATE_STRUCTURE':
                last_struct_change = a['date']
            elif a['type'] == 'OBS_PERIOD_OVERALL_OLDEST':
                data_start = a['title']
            elif a['type'] == 'OBS_PERIOD_OVERALL_LATEST':
                data_end = a['title']

        rows.append(
            {
                'title': title,
                'code': code,
                'type': _type,
                'last_update_of_data': last_update,
                'last_table_structure_change': last_struct_change,
                'data_start': data_start,
                'data_end': data_end,
            }
        )

    return rows


def _get_dims_info(
    code: str, detail: str = 'name', lang: str = 'en'
) -> tuple[str, str, DimsResult]:
    """Get dimension information for a dataset.

    Returns ``(agency_id, provider, dims)`` where the shape of ``dims``
    depends on ``detail`` (e.g. ``list[str | None]`` for ``name``,
    ``list[tuple[...]]`` for the other variants).
    """
    found = False
    i = 0
    df_root: ET.Element | None = None
    provider = ''
    agency_id = ''

    df_tail = (
        '/latest?detail=referencepartial&references=descendants'
        if detail == 'descr'
        else '/latest'
    )

    while not found and i < len(AGENCY_BY_PROVIDER):
        provider, agency_id = AGENCY_BY_PROVIDER[i]
        df_url = f'{BASE_URL[provider]}dataflow/{agency_id}/{code}{df_tail}'

        data = _retry_request(df_url)
        if data is not None:
            try:
                df_root = ET.fromstring(data)
                found = True
                if detail == 'empty':
                    return (agency_id, provider, [])
            except ET.ParseError:
                pass
        i += 1

    if not found or df_root is None:
        raise ValueError(f'Dataset not found: {code}')

    dsd_ref = df_root.find(dsd_path)
    if dsd_ref is None:
        raise ValueError(f'DSD reference not found for {code}')
    dsd_code = dsd_ref.get('id')
    dsd_url = f'{BASE_URL[provider]}datastructure/{agency_id}/{dsd_code}/latest'

    data = _retry_request(dsd_url)
    if data is None:
        raise ConnectionError(f'Failed to fetch DSD for {code}')

    dsd_root = ET.fromstring(data)

    dims: DimsResult
    if detail == 'name':
        dims = [dim.get('id') for dim in dsd_root.findall(dim_path)]
    elif detail == 'basic':
        basic_dims: list[tuple[str | None, str | None]] = []
        for dim in dsd_root.findall(dim_path):
            ref = dim.find(ref_path)
            ref_id = ref.get('id') if ref is not None else None
            basic_dims.append((dim.get('id'), ref_id))
        dims = basic_dims
    elif detail == 'order':
        dims = [
            (dim.get('position'), dim.get('id'))
            for dim in dsd_root.findall(dim_path)
        ]
    elif detail == 'descr':
        descr = df_root.findall(codelist_path)
        descr_dims: list[tuple[str | None, str | None, str | None]] = []
        for dim1 in dsd_root.findall(dim_path):
            ref1 = dim1.find(ref_path)
            dimension_id = ref1.get('id') if ref1 is not None else None
            full_name: str | None = None
            description: str | None = None
            for dim in descr:
                if dim.get('id') == dimension_id:
                    for d in dim.findall(XMLSNS_C + 'Name'):
                        if d.get(XMLSNS_L, None) == lang:
                            full_name = d.text
                    if full_name is None:
                        full_name = dim.findtext(XMLSNS_C + 'Name')
                    description = dim.findtext(XMLSNS_C + 'Description')
                    break
            descr_dims.append((dim1.get('id'), full_name, description))
        dims = descr_dims
    else:
        dims = []

    return (agency_id, provider, dims)


def get_pars(code: str) -> list[str]:
    """Get parameters (dimensions) for a dataset."""
    _debug(f'Fetching parameters for dataset: {code}', '📊')
    _, _, dims_raw = _get_dims_info(code, detail='name')
    # For detail='name' the concrete arm of the union is list[str | None].
    dims = cast(list[str | None], dims_raw)
    _debug(f'Found {len(dims)} parameters: {dims}', '✓')
    return [d for d in dims if d is not None]


def get_dic(
    code: str, par: str | None = None, full: bool = True, lang: str = 'en'
) -> list[tuple[str, str]]:
    """Get dictionary/codelist for dataset dimensions or parameter values."""
    _debug(f'Fetching dictionary for code={code}, par={par}', '📖')
    if par:
        agency_id, provider, dims_raw = _get_dims_info(code, detail='basic')
        # For detail='basic' the concrete arm is list[tuple[str | None, str | None]].
        # In practice every Dimension element has an ``id``, so we treat the
        # first tuple slot as a non-None str (matches original behaviour).
        dims = cast(list[tuple[str, str]],dims_raw)
        try:
            par_id = [d[1] for d in dims if d[0].lower() == par.lower()][0]
        except IndexError:
            _debug(f'Parameter {par} not found', '❌')
            raise ValueError(f'Parameter {par} not found in {code}')

        url = (
            f'{BASE_URL[provider]}codelist/{agency_id}/{par_id}/'
            f'latest?format=TSV&compressed=true&lang={lang}'
        )

        data = _retry_request(url)
        if data is None:
            _debug('Failed to fetch codelist', '❌')
            raise ConnectionError(f'Failed to fetch codelist for {par}')

        _debug('Decompressing and parsing TSV...')
        resp_list = gzip.decompress(data).decode('utf-8').split('\r\n')
        resp_list.pop()
        tmp_list: list[tuple[str, str]] = []
        for el in resp_list:
            split = el.split('\t')
            if len(split) >= 2:
                tmp_list.append((split[0], split[1]))
        _debug(f'Parsed {len(tmp_list)} code-label pairs', '✓')

        if full:
            return tmp_list
        else:
            par_values = get_par_values(code, par)
            return [el for el in tmp_list if el[0] in par_values]
    else:
        _, _, dims_list = _get_dims_info(code, detail='descr', lang=lang)
        _debug(f'Got {len(dims_list)} dimension descriptions', '✓')
        # detail='descr' yields list[tuple[str | None, str | None, str | None]]
        return cast(list[tuple[str, str]],dims_list)


def get_par_values(code: str, par: str) -> list[str]:
    """Get available values for a parameter in a dataset."""
    agency_id, provider, _ = _get_dims_info(code, detail='empty')
    url = f'{BASE_URL[provider]}contentconstraint/{agency_id}/{code}'

    data = _retry_request(url)
    if data is None:
        raise ConnectionError(f'Failed to fetch parameter values for {code}')

    root = ET.fromstring(data)
    par_values: list[str] = []

    for kv in root.findall(par_path):
        kv_id = kv.get('id')
        if kv_id is not None and kv_id.lower() == par.lower():
            for v in kv.findall(val_path):
                if v.text is not None:
                    par_values.append(v.text)

    return par_values


def get_data(
    code: str,
    flags: bool = False,
    filter_pars: dict[str, str | list[str]] | None = None,
) -> dict[str, list[str] | list[list[DataValue]]] | None:
    """Download Eurostat dataset as dictionary with columns and data."""
    if filter_pars is None:
        filter_pars = {}

    _, provider, dims_raw = _get_dims_info(code, detail='order')
    # For detail='order' the concrete arm is list[tuple[str | None, str | None]].
    # In practice both ``position`` and ``id`` are always present on
    # Dimension elements, so we treat the slots as ``str`` (matches the
    # original runtime behaviour where ``dict(c).get(j[1], '')`` was called
    # without a None-guard).
    dims = cast(list[tuple[str, str]],dims_raw)

    if not filter_pars:
        filt = ['?']
    else:
        start = ''
        end = ''
        nontime_pars: dict[str, list[str]] = {}

        for k, v in filter_pars.items():
            if k == 'startPeriod':
                start = f'startPeriod={v}&'
            elif k == 'endPeriod':
                end = f'endPeriod={v}&'
            else:
                nontime_pars[k] = v if isinstance(v, list) else [v]

        if nontime_pars:
            filter_lists = [
                tuple(
                    zip([d] * len(nontime_pars[str(d)]), nontime_pars[str(d)])
                )
                for d in nontime_pars
            ]
            cart = list(product(*filter_lists))
            filter_str_list = [
                '.'.join([dict(c).get(j[1], '') for j in sorted(dims)])
                for c in cart
            ]
            filt = [f'/{f}?{start}{end}' for f in filter_str_list]
        else:
            filt = [f'?{start}{end}']

    alldata: list[list[DataValue]] = []
    header: list[str] | None = None

    for f_str in filt:
        data_url = (
            f'{BASE_URL[provider]}data/{code}{f_str}format=TSV&compressed=true'
        )

        data = _retry_request(data_url)
        if data is None:
            continue

        dec = gzip.decompress(data).decode('utf-8')
        raw_data = dec.split('\r\n')

        for row_str in raw_data:
            if not row_str:
                continue

            if header is None:
                # Parse header: first column is "dim1,dim2,dim3", rest are time periods
                header_parts = row_str.split('\t')
                dimension_names = [
                    d.strip() for d in header_parts[0].split(',')
                ]
                time_periods = [t.strip() for t in header_parts[1:]]
                # Combine dimension names and time periods into full column list
                header = dimension_names + time_periods
                _debug(
                    f'Parsed header: {len(dimension_names)} dimensions + {len(time_periods)} periods',
                    '📊',
                )
                continue

            parts = row_str.split('\t')
            if len(parts) >= 2:
                key_parts: list[DataValue] = list(parts[0].split(','))
                values = parts[1:]

                if flags:
                    row_data_flags: list[DataValue] = []
                    for val in values:
                        val = val.strip()
                        if val == ':' or val == '':
                            row_data_flags.extend([None, ''])
                        elif ' ' in val:
                            v, f = val.split(' ', 1)
                            # Convert value to None if it's ":"
                            v_clean: str | None = None if v == ':' else v
                            row_data_flags.extend([v_clean, f])
                        else:
                            row_data_flags.extend([val, ''])
                    alldata.append(key_parts + row_data_flags)
                else:
                    row_data: list[DataValue] = []
                    for val in values:
                        val = val.strip()
                        # Handle missing data markers
                        if val == ':' or val == '':
                            row_data.append(None)
                        else:
                            # Remove flag if present
                            cleaned = val.split(' ')[0]
                            # Convert ":" to None even after flag removal
                            if cleaned == ':':
                                row_data.append(None)
                            else:
                                # Try to convert to number
                                try:
                                    row_data.append(float(cleaned))
                                except (ValueError, IndexError):
                                    row_data.append(cleaned)
                    alldata.append(key_parts + row_data)

    if not alldata or header is None:
        _debug('No data found', '⚠')
        return None

    _debug(f'Parsed {len(alldata)} rows with {len(header)} columns', '✓')
    return {'columns': header, 'data': alldata}


def setproxy(proxyinfo: object) -> None:
    """Compatibility function for eurostat package interface."""
    pass


# GISCO API functions
def gisco_request_blocking(url: str) -> bytes:
    """Make a blocking HTTP GET request for GISCO data (using QGIS settings).

    Args:
        url: URL to request

    Returns:
        Response data as bytes
    """
    from eurostat_downloader.src.settings import GLOBAL_SETTINGS
    from qgis.PyQt.QtCore import QUrl
    from qgis.PyQt.QtNetwork import QNetworkRequest

    _debug(f'GISCO blocking request: {url[:100]}...', '🗺')
    request = QNetworkRequest(QUrl(url))
    response = GLOBAL_SETTINGS.network_manager.blockingGet(request)
    # QGIS PyQt stubs return Any from content().data(); cast to bytes
    data = cast(bytes, response.content().data())
    _debug(f'Received {len(data)} bytes', '✓')
    return data


def gisco_request(
    url: str, manager: QgsNetworkAccessManager | None = None
) -> QNetworkReply:
    """Make an async HTTP GET request for GISCO data.

    Args:
        url: URL to request
        manager: Optional QgsNetworkAccessManager instance

    Returns:
        QNetworkReply object
    """
    from eurostat_downloader.src.settings import GLOBAL_SETTINGS
    from qgis.PyQt.QtCore import QUrl
    from qgis.PyQt.QtNetwork import QNetworkRequest

    _debug(f'GISCO async request: {url[:100]}...', '🗺')
    request = QNetworkRequest(QUrl(url))
    if manager is None:
        manager = GLOBAL_SETTINGS.network_manager
    return manager.get(request)
