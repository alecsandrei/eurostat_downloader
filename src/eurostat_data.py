from typing import (
    Union,
    Optional
)
from enum import Enum
from dataclasses import (
    dataclass,
    field
)
from itertools import product
import concurrent.futures

import eurostat
import pandas as pd

from .utils import handle_ssl_error


class TOCColumns(Enum):
    """Enumerates the table of contents column names."""
    TITLE = 'title'
    CODE = 'code'


class Language(Enum):
    ENGLISH = 'en'
    FRENCH = 'fr'
    GERMAN = 'de'


TableOfContents = dict[Language, pd.DataFrame]


@dataclass
class Database:
    lang: Language = field(default=Language.ENGLISH)
    _toc: TableOfContents = field(init=False, default_factory=dict)

    def set_language(self, lang: Language):
        self.lang = lang

    def initialize_toc(self):
        """Used to initialize the table of contents."""
        with concurrent.futures.ThreadPoolExecutor() as executor:
            executor.map(self._set_toc, Language)

    @handle_ssl_error
    def _set_toc(self, lang: Language):
        self._toc[lang] = eurostat.get_toc_df(lang=lang.value)

    @property
    def toc(self) -> pd.DataFrame:
        return self._toc[self.lang]

    @property
    def toc_titles(self):
        return self.toc[TOCColumns.TITLE.value]

    @property
    def toc_size(self):
        return self.toc.shape[0]

    def get_subset(self, keyword: str):
        """Creates a subset of the toc."""
        if not keyword.strip():
            return self.toc
        # Concat the code and the title.
        concatenated = (
            self.toc[TOCColumns.CODE.value]
            + ' '
            + self.toc[TOCColumns.TITLE.value]
        )
        # Check if keyword is in series.
        mask = concatenated.str.contains(pat=keyword, case=False, regex=False)
        # Concat the dataframes and drop duplicates.
        return self.toc[mask]

    def get_titles(self, subset: Optional[pd.DataFrame] = None):
        if subset is None:
            subset = self.toc
        return subset[TOCColumns.TITLE.value]

    def get_codes(
        self,
        subset: Optional[Union[pd.DataFrame, pd.Series]] = None
    ):
        if subset is None:
            subset = self.toc
        return subset[TOCColumns.CODE.value]


ParamsInfo = dict[Language, dict[str, list[tuple[str, str]]]]


@dataclass
class Dataset:
    """Class to represent a specific dataset from Eurostat."""
    db: Database
    code: str
    lang: Optional[Language] = field(default=None)
    _param_info: ParamsInfo = field(init=False, default_factory=dict)
    _df: pd.DataFrame = field(init=False)
    _params: list[str] = field(init=False, default_factory=list)

    def set_language(self, lang: Optional[Language]):
        self.lang = lang

    @handle_ssl_error
    def _set_pars(self):
        self._params.extend(eurostat.get_pars(self.code))

    @handle_ssl_error
    def _set_param_info(self, data: tuple[str, Language]):
        param, lang = data[0], data[1]
        dic = eurostat.get_dic(
            code=self.code, par=param, full=False, lang=lang.value
        )
        self._param_info.setdefault(lang, {})[param] = dic

    @handle_ssl_error
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
    def title(self):
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
