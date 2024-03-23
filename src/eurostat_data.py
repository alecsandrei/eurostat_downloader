from typing import (
    Union,
    Literal,
    Optional
)
from functools import (
    cached_property,
    lru_cache,
)
from enum import Enum
from dataclasses import (
    dataclass,
    field
)

import eurostat
import pandas as pd


class TOCColumns(Enum):
    """Enumerates the table of contents column names."""
    TITLE = 'title'
    CODE = 'code'


@dataclass(frozen=True, eq=True)
class Database:

    @cached_property
    def toc(self):
        return eurostat.get_toc_df()

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

    def get_titles(self, subset: Union[None, pd.DataFrame] = None):
        if subset is None:
            subset = self.toc
        return subset[TOCColumns.TITLE.value]

    def get_codes(self, subset: Union[None, pd.DataFrame, pd.Series] = None):
        if subset is None:
            subset = self.toc
        return subset[TOCColumns.CODE.value]


class Language(Enum):
    ENGLISH = 'en'
    FRENCH = 'fr'
    GERMAN = 'de'


Lang = Literal[Language.ENGLISH, Language.FRENCH, Language.GERMAN]


@dataclass(frozen=True, eq=True)
class Dataset:
    """Class to represent a specific dataset from Eurostat."""
    db: Database
    code: str
    lang: Optional[Lang] = field(default=None)

    def set_language(self, lang: Optional[Lang]):
        object.__setattr__(self, 'lang', lang)

    @cached_property
    def df(self) -> pd.DataFrame:
        df = eurostat.get_data_df(code=self.code)
        assert df is not None
        self.remove_time_period_str(df=df)
        return df

    @staticmethod
    def remove_time_period_str(df: pd.DataFrame):
        def replace(col: str):
            return col.replace(r'\TIME_PERIOD', '')
        df.columns = df.columns.map(replace)

    @cached_property
    def title(self):
        return self.db.toc.loc[
            self.db.toc[TOCColumns.CODE.value]
            == self.code, TOCColumns.TITLE.value
        ]

    @cached_property
    def frequency(self) -> str:
        """Assumes that the first column contains the frequency,
        and that all the values inside the column are all unique."""
        return self.df.iloc[0].values[0]

    @cached_property
    def data_start(self):
        return self.date_columns[0]

    @cached_property
    def data_end(self):
        return self.date_columns[-1]

    @cached_property
    def date_columns(self):
        return self.df.columns[len(self.params):]

    @cached_property
    def params(self) -> list[str]:
        return eurostat.get_pars(self.code)

    def get_dic_kwargs(self):
        kwargs = {}
        if self.lang is not None:
            kwargs['lang'] = self.lang.value
        return kwargs

    @lru_cache(maxsize=128)
    def get_param_full_name(self, param: str) -> list[tuple[str, str]]:
        return eurostat.get_dic(
            code=self.code, par=param, full=False, **self.get_dic_kwargs()
        )  # type: ignore
