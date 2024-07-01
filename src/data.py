from __future__ import annotations

from typing import TYPE_CHECKING
from enum import (
    Enum,
    auto
)
from dataclasses import (
    dataclass,
    field
)
from itertools import product
import concurrent.futures

from . import eurostat
import pandas as pd

if TYPE_CHECKING:
    from .settings import ProxySettings


class TOCColumns(Enum):
    """Enumerates the table of contents column names."""
    TITLE = 'title'
    CODE = 'code'


class Language(Enum):
    ENGLISH = 'en'
    FRENCH = 'fr'
    GERMAN = 'de'


class Agency(Enum):
    EUROSTAT = 'EUROSTAT'
    COMEXT = 'COMEXT'
    COMP = 'COMP'
    EMPL = 'EMPL'
    GROW = 'GROW'


class ConnectionStatus(Enum):
    AVAILABLE = auto()
    UNAVAILABLE = auto()


TableOfContents = dict[Agency, dict[Language, pd.DataFrame]]
AgencyStatus = dict[Agency, ConnectionStatus]


def set_eurostat_proxy(proxy_settings: ProxySettings) -> None:
    if proxy_settings.host and proxy_settings.port:
        # Create a dictionary with the proxy information
        proxy_info = {
            'https': [
                proxy_settings.user,
                proxy_settings.password,
                f'http://{proxy_settings.host}:{proxy_settings.port}'
            ]
        }
        # Set the proxy for the eurostat library
        eurostat.setproxy(proxy_info)


@dataclass
class Database:
    lang: Language = field(default=Language.ENGLISH)
    _toc: TableOfContents = field(init=False, default_factory=dict)
    _agency_status: AgencyStatus = field(init=False, default_factory=dict)

    def set_language(self, lang: Language):
        self.lang = lang

    def initialize_toc(self):
        """Used to initialize the table of contents."""
        with concurrent.futures.ThreadPoolExecutor() as executor:
            results = executor.map(
                self._set_toc, product(Language, Agency)
            )
        for result in results:
            if result is not None:
                result.exception()

    def _set_toc(
        self,
        params: tuple[Language, Agency]
    ):
        lang, agency = params
        self._toc.setdefault(agency, {})
        # If status was for this agency was already unavailable, return
        status = self._agency_status.get(agency, None)
        if status is not None:
            if status == ConnectionStatus.UNAVAILABLE:
                return None
        try:
            self._toc[agency][lang] = (
                eurostat.get_toc_df(agency=agency.value, lang=lang.value)
            )
            self._agency_status[agency] = ConnectionStatus.AVAILABLE
        except ConnectionError:
            self._agency_status[agency] = ConnectionStatus.UNAVAILABLE

    def _get_toc(self, lang: Language) -> pd.DataFrame:
        toc = pd.DataFrame()
        for data in self._toc.values():
            if (df := data.get(lang, None)) is not None:
                toc = pd.concat([toc, df], ignore_index=True)
        return toc

    @property
    def toc(self) -> pd.DataFrame:
        return self._get_toc(self.lang)

    @property
    def toc_titles(self) -> pd.Series[str]:
        return self.toc[TOCColumns.TITLE.value]

    @property
    def toc_size(self):
        return self.toc.shape[0]

    def get_subset(self, keyword: str):
        """Creates a subset of the toc."""
        if not keyword.strip():
            return self.toc
        # Concat the code and the title.
        concatenated: pd.Series[str] = (
            self.toc[TOCColumns.CODE.value]
            + ' '
            + self.toc[TOCColumns.TITLE.value]
        )
        # Check if keyword is in series.
        mask = concatenated.str.contains(pat=keyword, case=False, regex=False)
        # Concat the dataframes and drop duplicates.
        return self.toc[mask]

    def get_titles(self, subset: pd.DataFrame | None = None) -> pd.Series[str]:
        if subset is None:
            subset = self.toc
        return subset[TOCColumns.TITLE.value]

    def get_codes(
        self,
        subset: pd.DataFrame | None = None
    ) -> pd.Series[str]:
        if subset is None:
            subset = self.toc
        return subset[TOCColumns.CODE.value]


ParamsInfo = dict[Language, dict[str, list[tuple[str, str]]]]


@dataclass
class Dataset:
    """Class to represent a specific dataset from Eurostat."""
    db: Database
    code: str
    lang: Language | None = field(default=None)
    _param_info: ParamsInfo = field(init=False, default_factory=dict)
    _df: pd.DataFrame = field(init=False)
    _params: list[str] = field(init=False, default_factory=list)

    def set_language(self, lang: Language | None):
        self.lang = lang

    def _set_pars(self):
        self._params.extend(eurostat.get_pars(self.code))

    def _set_param_info(self, data: tuple[str, Language]):
        param, lang = data[0], data[1]
        dic = eurostat.get_dic(
            code=self.code, par=param, full=False, lang=lang.value
        )
        self._param_info.setdefault(lang, {})[param] = dic

    def _set_df(self):
        data_df = eurostat.get_data_df(code=self.code)
        assert data_df is not None
        self.remove_time_period_str(data_df)
        self._df = data_df

    def initialize_df(self):
        with concurrent.futures.ThreadPoolExecutor() as executor:
            executor.submit(self._set_df)
            params = executor.submit(self._set_pars)
            concurrent.futures.wait([params])
            executor.map(self._set_param_info, product(self._params, Language))

    @property
    def df(self) -> pd.DataFrame:
        return self._df

    @staticmethod
    def remove_time_period_str(df: pd.DataFrame):
        def replace(col: str):
            return col.replace(r'\TIME_PERIOD', '')
        df.columns = df.columns.map(replace)

    @property
    def title(self) -> str:
        return self.db.toc.loc[
            self.db.toc[TOCColumns.CODE.value]
            == self.code, TOCColumns.TITLE.value
        ].iloc[0]

    @property
    def frequency(self) -> str:
        """Assumes that the first column contains the frequency,
        and that all the values inside the column are all unique."""
        return self.df.iloc[0].values[0]

    @property
    def data_start(self):
        return self.date_columns[0]

    @property
    def data_end(self):
        return self.date_columns[-1]

    @property
    def date_columns(self):
        return self.df.columns[len(self.params):]

    @property
    def params(self) -> list[str]:
        return self._params

    @property
    def params_info(self) -> ParamsInfo:
        return self._param_info
