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

from . import DEBUG, PACKAGE_DIR, fetch
from .enums import Agency, ConnectionStatus, Language, TableOfContentsColumn
from .settings import GLOBAL_SETTINGS


def _debug(msg: str, prefix: str = "🔍") -> None:
    """Print debug message if DEBUG mode is enabled."""
    if DEBUG:
        print(f"{prefix} [EUROSTAT-DATA] {msg}")

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
Datasets = dict[str, t.Any]
TableOfContents = dict[Agency, dict[Language, list[dict[str, t.Any]]]]
AgencyStatus = dict[Agency, ConnectionStatus]


@dataclass
class Database:
    lang: Language = field(default=Language.ENGLISH)
    _toc: TableOfContents = field(init=False, default_factory=dict)
    _agency_status: AgencyStatus = field(init=False, default_factory=dict)
    _cache_path: Path = field(init=False)

    def __post_init__(self):
        self._cache_path = (
            PACKAGE_DIR.parent
            / 'assets'
            / 'eurostat_cache'
            / f'eurostat_toc_{datetime.today().strftime("%Y-%m-%d")}.json'
        )
        self._cache_path.parent.mkdir(exist_ok=True)

    def set_language(self, lang: Language):
        self.lang = lang

    def initialize_toc(self):
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

    def _set_toc(self, params: tuple[Language, Agency]):
        lang, agency = params
        self._toc.setdefault(agency, {})
        # If status was for this agency was already unavailable, return
        status = self._agency_status.get(agency, None)
        if status is not None:
            if status == ConnectionStatus.UNAVAILABLE:
                return None
        try:
            self._toc[agency][lang] = fetch.get_toc(
                agency=agency.value, lang=lang.value
            )
            self._agency_status[agency] = ConnectionStatus.AVAILABLE
        except ConnectionError:
            self._agency_status[agency] = ConnectionStatus.UNAVAILABLE

    def _get_toc(self, lang: Language) -> list[dict[str, t.Any]]:
        rows = []
        for data in self._toc.values():
            if (toc_list := data.get(lang, None)) is not None:
                rows.extend(toc_list)
        return sorted(rows, key=lambda x: x.get('code', ''))

    @property
    def toc(self) -> list[dict[str, t.Any]]:
        return self._get_toc(self.lang)

    @property
    def toc_titles(self) -> list[str]:
        return [row[TableOfContentsColumn.TITLE.value] for row in self.toc]

    @property
    def toc_size(self):
        return len(self.toc)

    def get_subset(self, keyword: str) -> list[dict[str, t.Any]]:
        """Creates a subset of the toc."""
        if not keyword.strip():
            return self.toc
        keyword_lower = keyword.lower()
        result = []
        for row in self.toc:
            code = row.get(TableOfContentsColumn.CODE.value, '')
            title = row.get(TableOfContentsColumn.TITLE.value, '')
            search_text = f'{code} {title}'.lower()
            if keyword_lower in search_text:
                result.append(row)
        return result

    def get_titles(
        self, subset: list[dict[str, t.Any]] | None = None
    ) -> list[str]:
        if subset is None:
            subset = self.toc
        return [row[TableOfContentsColumn.TITLE.value] for row in subset]

    def get_codes(
        self, subset: list[dict[str, t.Any]] | None = None
    ) -> list[str]:
        if subset is None:
            subset = self.toc
        return [row[TableOfContentsColumn.CODE.value] for row in subset]

    def _load_toc_from_cache(self):
        """Load table of contents from JSON cache."""
        with open(self._cache_path, mode='r', encoding='utf-8') as file:
            cache_data = json.load(file)

        for agency_name, languages_data in cache_data.items():
            agency = Agency[agency_name]
            self._toc[agency] = {}
            for lang_name, toc_data in languages_data.items():
                lang = Language[lang_name]
                self._toc[agency][lang] = toc_data

    def cache_toc(self):
        """Cache table of contents as JSON."""
        cache_data = {}
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
    _data: dict[str, t.Any] | None = field(init=False, default=None)
    _params: list[str] = field(init=False, default_factory=list)

    def set_language(self, lang: Language | None):
        self.lang = lang

    def _set_pars(self):
        self._params.extend(fetch.get_pars(self.code))

    def _set_param_info(self, data: tuple[str, Language]):
        param, lang = data[0], data[1]
        dic = fetch.get_dic(code=self.code, par=param, full=False, lang=lang.value)
        self._param_info.setdefault(lang, {})[param] = dic

    def _set_data(self):
        _debug(f'Fetching dataset: {self.code}', '💾')
        data_dict = fetch.get_data(code=self.code)
        assert data_dict is not None
        self.remove_time_period_str(data_dict)
        _debug(
            f'Dataset loaded: {len(data_dict["data"])} rows, {len(data_dict["columns"])} columns',
            '✓',
        )
        self._data = data_dict

    def initialize_data(self):
        _debug(f'Initializing dataset: {self.code}', '⚙')
        with concurrent.futures.ThreadPoolExecutor() as executor:
            executor.submit(self._set_data)
            params = executor.submit(self._set_pars)
            concurrent.futures.wait([params])
            executor.map(self._set_param_info, product(self._params, Language))
        _debug('Dataset initialized successfully', '✓')

    @property
    def data(self) -> dict[str, t.Any]:
        """Returns data as dict with 'columns' and 'data' keys."""
        return self._data

    @staticmethod
    def remove_time_period_str(data_dict: dict[str, t.Any]):
        """Remove \\TIME_PERIOD from column names."""
        columns = data_dict['columns']
        data_dict['columns'] = [
            col.replace(r'\TIME_PERIOD', '') for col in columns
        ]

    @property
    def title(self) -> str:
        for row in self.db.toc:
            if row[TableOfContentsColumn.CODE.value] == self.code:
                return row[TableOfContentsColumn.TITLE.value]
        return ''

    @property
    def frequency(self) -> str:
        """Assumes that the first column contains the frequency,
        and that all the values inside the column are all unique."""
        if self._data and self._data['data']:
            return self._data['data'][0][0]
        return ''

    @property
    def data_start(self):
        date_cols = self.date_columns
        return date_cols[0] if date_cols else None

    @property
    def data_end(self):
        date_cols = self.date_columns
        return date_cols[-1] if date_cols else None

    @property
    def date_columns(self):
        if not self._data:
            return []
        return self._data['columns'][len(self.params) :]

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
        return getattr(self, field_name)


class Units(UserList[Unit]):
    def __init__(self, units: c.Iterable[Unit] | None = None):
        super().__init__(units)

    def as_dicts(self) -> list[dict]:
        return [asdict(unit) for unit in self.data]

    @classmethod
    def from_json(cls: t.Type[t.Self], json: dict[str, t.Any]) -> t.Self:
        items = []
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

    def filter(self, filters: dict[str, c.Sequence[str]]) -> Units:
        units = []
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

    def set_datasets(self):
        url = GISCO_URL['datasets'].format(theme=self.theme)
        self.datasets = json.loads(fetch.gisco_request_blocking(url))

    def get_years(self) -> list[str]:
        if self.datasets is None:
            self.set_datasets()
        assert self.datasets is not None
        return [
            dataset_id.split('-')[1] for dataset_id in reversed(self.datasets)
        ]

    def set_units(self, year: str):
        url = GISCO_URL['units'].format(theme=self.theme, year=year)
        self.units[year] = Units.from_json(json.loads(fetch.gisco_request_blocking(url)))

    def get_units(self, year: str) -> Units:
        if year not in self.units:
            self.set_units(year)
        return self.units[year]

    def get_feature_from_unit(self, unit: Unit, manager=None):
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
