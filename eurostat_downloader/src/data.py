from __future__ import annotations

import abc
import collections.abc as c
import concurrent.futures
import json
import typing as t
from collections import UserList, defaultdict
from dataclasses import asdict, dataclass, field
from datetime import datetime
from functools import cached_property
from itertools import product
from pathlib import Path
from urllib.parse import urljoin

from qgis.core import QgsNetworkAccessManager
from qgis.PyQt.QtNetwork import QNetworkReply

from eurostat_downloader.src import DEBUG, PACKAGE_DIR, fetch
from eurostat_downloader.src.enums import Agency, ConnectionStatus, Language, TableOfContentsColumn
from eurostat_downloader.src.settings import GLOBAL_SETTINGS


class TocRow(t.TypedDict, total=False):
    title: str
    code: str
    type: str
    level: int
    agency: str
    values: str
    last_update_of_data: str
    last_table_structure_change: str
    data_start: str
    data_end: str


# Cell values from the Eurostat dataset endpoint: numeric values are parsed
# as ``float``, missing data is ``None``, and the leading key columns plus
# any flag columns are ``str``.
DatasetCell = float | str | None


class DatasetPayload(t.TypedDict):
    """Shape of the dict returned by :func:`fetch.get_data`."""

    columns: list[str]
    data: list[list[DatasetCell]]


class UnitDict(t.TypedDict):
    """Serialized form of :class:`Unit` (matches its dataclass fields)."""

    id: str
    spatial_type: str
    scale: str | None
    projection: str
    year: str


def _debug(msg: str, prefix: str = '🔍') -> None:
    """Print debug message if DEBUG mode is enabled."""
    if DEBUG:
        print(f'{prefix} [EUROSTAT-DATA] {msg}')


GISCO_BASE = 'https://gisco-services.ec.europa.eu/distribution/v2/{theme}/'
GISCO_URL = {
    'datasets': urljoin(GISCO_BASE, 'datasets.json'),
    'units': urljoin(GISCO_BASE, '{theme}-{year}-units.json'),
    'label': urljoin(GISCO_BASE, '{id}-label-{projection}-{year}.geojson'),
    'region': urljoin(
        GISCO_BASE, '{id}-region-{scale}-{projection}-{year}.geojson'
    ),
    'unit': urljoin(GISCO_BASE, 'distribution/{filename}'),
}
# GISCO ``datasets.json`` is a mapping of dataset id -> heterogeneous metadata
# object (mixed strings, lists, nested dicts). We only ever read keys/iterate,
# never inspect the values, so ``object`` is precise enough.
Datasets = dict[str, object]
TableOfContents = dict[Agency, dict[Language, list[TocRow]]]
AgencyStatus = dict[Agency, ConnectionStatus]


@dataclass
class Database:
    lang: Language = field(default=Language.ENGLISH)
    _toc: TableOfContents = field(init=False, default_factory=dict)
    _agency_status: AgencyStatus = field(init=False, default_factory=dict)
    _cache_path: Path = field(init=False)

    def __post_init__(self) -> None:
        self._cache_path = (
            PACKAGE_DIR.parent
            / 'assets'
            / 'eurostat_cache'
            / f'eurostat_toc_{datetime.today().strftime("%Y-%m-%d")}.json'
        )
        self._cache_path.parent.mkdir(exist_ok=True)

    def set_language(self, lang: Language) -> None:
        self.lang = lang

    def initialize_toc(self) -> None:
        """Used to initialize the table of contents."""
        if DEBUG and self._cache_path.exists():
            self._load_toc_from_cache()
        else:
            with concurrent.futures.ThreadPoolExecutor() as executor:
                results = executor.map(
                    self._set_toc, product(Language, GLOBAL_SETTINGS.agencies)
                )
            for result in results:
                if result is not None:
                    result.exception()
            if DEBUG:
                self.cache_toc()

    def _set_toc(self, params: tuple[Language, Agency]) -> None:
        lang, agency = params
        self._toc.setdefault(agency, {})
        # If status was for this agency was already unavailable, return
        status = self._agency_status.get(agency, None)
        if status is not None:
            if status == ConnectionStatus.UNAVAILABLE:
                return None
        try:
            # ``fetch.get_toc`` is typed as ``list[dict[str, Any]]``; each row
            # matches the ``TocRow`` schema, so cast to keep the rest of the
            # module ``Any``-free.
            self._toc[agency][lang] = t.cast(
                'list[TocRow]',
                fetch.get_toc(agency=agency.value, lang=lang.value),
            )
            self._agency_status[agency] = ConnectionStatus.AVAILABLE
        except ConnectionError:
            self._agency_status[agency] = ConnectionStatus.UNAVAILABLE

    def _get_toc(self, lang: Language) -> list[TocRow]:
        """Get TOC for current language, organized by agency.

        Note: Items are kept in their original hierarchical order from the API.
        We only sort by agency to group items, but preserve the tree structure
        within each agency.
        """
        rows = []
        for agency in sorted(self._toc.keys(), key=lambda a: a.value):
            data = self._toc[agency]
            if (toc_list := data.get(lang, None)) is not None:
                # Add agency info to each item for organization
                for item in toc_list:
                    item['agency'] = agency.value
                rows.extend(toc_list)
        return rows

    @property
    def toc(self) -> list[TocRow]:
        return self._get_toc(self.lang)

    @property
    def toc_titles(self) -> list[str]:
        return [row[TableOfContentsColumn.TITLE.value] for row in self.toc]

    @property
    def toc_size(self) -> int:
        return len(self.toc)

    def get_subset(self, keyword: str) -> list[TocRow]:
        """Creates a subset of the toc."""
        if not keyword.strip():
            return self.toc
        keyword_lower = keyword.lower()
        result: list[TocRow] = []
        for row in self.toc:
            code = row.get(TableOfContentsColumn.CODE.value, '')
            title = row.get(TableOfContentsColumn.TITLE.value, '')
            search_text = f'{code} {title}'.lower()
            if keyword_lower in search_text:
                result.append(row)
        return result

    def get_titles(
        self, subset: c.Sequence[TocRow] | None = None
    ) -> list[str]:
        if subset is None:
            subset = self.toc
        return [row[TableOfContentsColumn.TITLE.value] for row in subset]

    def get_codes(
        self, subset: c.Sequence[TocRow] | None = None
    ) -> list[str]:
        if subset is None:
            subset = self.toc
        return [row[TableOfContentsColumn.CODE.value] for row in subset]

    def _load_toc_from_cache(self) -> None:
        """Load table of contents from JSON cache."""
        with open(self._cache_path, mode='r', encoding='utf-8') as file:
            cache_data = json.load(file)

        for agency_name, languages_data in cache_data.items():
            agency = Agency[agency_name]
            self._toc[agency] = {}
            for lang_name, toc_data in languages_data.items():
                lang = Language[lang_name]
                self._toc[agency][lang] = toc_data

    def cache_toc(self) -> None:
        """Cache table of contents as JSON."""
        cache_data: dict[str, dict[str, list[TocRow]]] = {}
        for agency, languages_data in self._toc.items():
            cache_data[agency.name] = {}
            for lang, toc_list in languages_data.items():
                cache_data[agency.name][lang.name] = toc_list

        with open(self._cache_path, mode='w', encoding='utf-8') as file:
            json.dump(cache_data, file, indent=2)


ParamsInfo = dict[Language, dict[str, list[tuple[str, str]]]]


@dataclass
class Dataset:
    """Class to represent a specific dataset from Eurostat."""

    db: Database
    code: str
    lang: Language | None = field(default=None)
    _param_info: ParamsInfo = field(init=False, default_factory=dict)
    _data: DatasetPayload | None = field(init=False, default=None)
    _params: list[str] = field(init=False, default_factory=list)

    def set_language(self, lang: Language | None) -> None:
        self.lang = lang

    def _set_pars(self) -> None:
        self._params.extend(fetch.get_pars(self.code))

    def _set_param_info(self, data: tuple[str, Language]) -> None:
        param, lang = data[0], data[1]
        dic = fetch.get_dic(
            code=self.code, par=param, full=False, lang=lang.value
        )
        self._param_info.setdefault(lang, {})[param] = dic

    def _set_data(self) -> None:
        _debug(f'Fetching dataset: {self.code}', '💾')
        raw = fetch.get_data(code=self.code)
        assert raw is not None
        # ``fetch.get_data`` is typed as ``dict[str, Any] | None``; the
        # runtime shape matches ``DatasetPayload``.
        data_dict = t.cast(DatasetPayload, raw)
        self.remove_time_period_str(data_dict)
        _debug(
            f'Dataset loaded: {len(data_dict["data"])} rows, {len(data_dict["columns"])} columns',
            '✓',
        )
        self._data = data_dict

    def initialize_data(self) -> None:
        _debug(f'Initializing dataset: {self.code}', '⚙')
        with concurrent.futures.ThreadPoolExecutor() as executor:
            executor.submit(self._set_data)
            params = executor.submit(self._set_pars)
            concurrent.futures.wait([params])
            executor.map(self._set_param_info, product(self._params, Language))
        _debug('Dataset initialized successfully', '✓')

    @property
    def data(self) -> DatasetPayload | None:
        """Returns data as dict with 'columns' and 'data' keys."""
        return self._data

    @staticmethod
    def remove_time_period_str(data_dict: DatasetPayload) -> None:
        """Remove \\TIME_PERIOD from column names."""
        columns = data_dict['columns']
        data_dict['columns'] = [
            col.replace(r'\TIME_PERIOD', '') for col in columns
        ]

    @property
    def title(self) -> str:
        for row in self.db.toc:
            if row[TableOfContentsColumn.CODE.value] == self.code:
                return str(row[TableOfContentsColumn.TITLE.value])
        return ''

    @property
    def frequency(self) -> str:
        """Assumes that the first column contains the frequency,
        and that all the values inside the column are all unique."""
        if self._data and self._data['data']:
            return str(self._data['data'][0][0])
        return ''

    @property
    def data_start(self) -> str | None:
        date_cols = self.date_columns
        return date_cols[0] if date_cols else None

    @property
    def data_end(self) -> str | None:
        date_cols = self.date_columns
        return date_cols[-1] if date_cols else None

    @property
    def date_columns(self) -> list[str]:
        if not self._data:
            return []
        return list(self._data['columns'][len(self.params) :])

    @property
    def params(self) -> list[str]:
        return self._params

    @property
    def params_info(self) -> ParamsInfo:
        return self._param_info


@dataclass(frozen=True, eq=True)
class Unit:
    id: str
    spatial_type: str
    scale: str | None
    projection: str
    year: str

    @classmethod
    def from_filename(cls: t.Type[t.Self], filename: str) -> t.Self:
        split = filename.replace('.geojson', '').split('-')
        if split[1] == 'label':
            try:
                split.insert(2, None)  # type: ignore
            except Exception as e:
                raise e
        return cls(*split)

    def to_filename(self) -> str:
        vals = (
            self.id,
            self.spatial_type,
            self.scale,
            self.projection,
            self.year,
        )
        return '-'.join(val for val in vals if val is not None) + '.geojson'

    def __getitem__(self, field_name: str) -> str | None:
        value: str | None = getattr(self, field_name)
        return value


class Units(UserList[Unit]):
    def __init__(self, units: c.Iterable[Unit] | None = None) -> None:
        super().__init__(units)

    def as_dicts(self) -> list[UnitDict]:
        # ``asdict`` is typed as ``dict[str, Any]``; the runtime shape matches
        # ``UnitDict``.
        return [t.cast(UnitDict, asdict(unit)) for unit in self.data]

    @classmethod
    def from_json(
        cls: t.Type[t.Self], json: c.Mapping[str, c.Iterable[str]]
    ) -> t.Self:
        items: list[Unit] = []
        for name, units in json.items():
            for unit in units:
                items.append(Unit.from_filename(unit))
        return cls(items)

    def get_unique_field_values(
        self, field_names: c.Sequence[str] | None = None
    ) -> dict[str, list[str]]:
        values: dict[str, list[str]] = defaultdict(list)
        for unit in self.data:
            for field_name, value in asdict(unit).items():
                if field_names is not None and field_name not in field_names:
                    continue
                col = values[field_name]
                if value not in col:
                    col.append(value)
        return values

    def filter(self, filters: c.Mapping[str, c.Sequence[str]]) -> Units:
        units: list[Unit] = []
        for unit in self.data:
            append = True
            for field_name, values in filters.items():
                truthy_values = [value for value in values if value]
                if truthy_values and unit[field_name] not in truthy_values:
                    append = False
                    break
            if append:
                units.append(unit)
        return Units(units)


@dataclass
class GISCO(abc.ABC):
    datasets: Datasets | None = field(init=False, default=None)
    units: dict[str, Units] = field(init=False, default_factory=dict)

    @abc.abstractmethod
    @cached_property
    def theme(self) -> str: ...

    def set_datasets(self) -> None:
        url = GISCO_URL['datasets'].format(theme=self.theme)
        self.datasets = json.loads(fetch.gisco_request_blocking(url))

    def get_years(self) -> list[str]:
        if self.datasets is None:
            self.set_datasets()
        assert self.datasets is not None
        return [
            dataset_id.split('-')[1] for dataset_id in reversed(self.datasets)
        ]

    def set_units(self, year: str) -> None:
        url = GISCO_URL['units'].format(theme=self.theme, year=year)
        self.units[year] = Units.from_json(
            json.loads(fetch.gisco_request_blocking(url))
        )

    def get_units(self, year: str) -> Units:
        if year not in self.units:
            self.set_units(year)
        return self.units[year]

    def get_feature_from_unit(
        self,
        unit: Unit,
        manager: QgsNetworkAccessManager | None = None,
    ) -> QNetworkReply:
        filename = unit.to_filename()
        url = GISCO_URL['unit'].format(theme=self.theme, filename=filename)
        return fetch.gisco_request(url, manager)


@dataclass
class NUTS(GISCO):
    @property
    def theme(self) -> str:
        return 'nuts'


@dataclass
class UrbanAudit(GISCO):
    @property
    def theme(self) -> str:
        return 'urau'


@dataclass
class Countries(GISCO):
    @property
    def theme(self) -> str:
        return 'countries'
