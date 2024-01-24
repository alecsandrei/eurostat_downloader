from typing import (
    Union,
    Literal,
    Optional
)
from functools import (
    cached_property,
    lru_cache
)
from enum import Enum

import eurostat
import pandas as pd
from dataclasses import (
    dataclass,
    field
)


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

    # @lru_cache(maxsize=100)
    def get_subset(self, keyword: str):
        """Creates a subset of the toc."""
        if not keyword.strip():
            return self.toc
        keyword = keyword.lower()
        # Check if keyword is in code.
        code_mask = self.toc[TOCColumns.CODE.value].str.contains(pat=keyword, case=False)
        code_subset = self.toc[code_mask]
        # Check if keyword is in title.
        title_mask = self.toc[TOCColumns.TITLE.value].str.contains(pat=keyword, case=False)
        title_subset = self.toc[title_mask]
        # Concat the dataframes
        subset = pd.concat([code_subset, title_subset], axis='index').drop_duplicates(keep='first')
        subset.sort_values(by=TOCColumns.TITLE.value, inplace=True)
        return subset

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


@dataclass(frozen=True, eq=True)
class Dataset:
    """Class to represent a specific dataset from Eurostat."""
    db: Database
    code: str
    lang: Optional[Literal[Language.ENGLISH, Language.FRENCH, Language.GERMAN]] = field(default=None)

    def set_language(self, lang: Literal[Language.ENGLISH, Language.FRENCH, Language.GERMAN]):
        object.__setattr__(self, 'lang', lang)

    @cached_property
    def df(self) -> pd.DataFrame:
        df = eurostat.get_data_df(code=self.code)
        self.fix_df_columns(df=df)
        return df

    @staticmethod
    def fix_df_columns(df: pd.DataFrame):
        """At the time of writing the current code, in the eurostat package,
        a returned dataset dataframe from the 'get_data_df' method has '\\TIME PERIOD' added
        to it's last 'params' column (like this for example: 'GEO\\TIME_PERIOD').
        This function fixes that. Also, sometimes the columns are integers instead of strings."""
        df.columns = [str(col).replace(r'\TIME_PERIOD', '') for col in df.columns]

    @cached_property
    def title(self):
        return self.db.toc.loc[self.db.toc[TOCColumns.CODE.value] == self.code, TOCColumns.TITLE.value]
    
    @cached_property
    def frequency(self):
        """Assumes that the first column contains the frequency, and that all the values
        inside the column are all unique."""
        return self.df.iloc[0, 0]

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
    def params(self):
        return eurostat.get_pars(self.code)

    def get_dic_kwargs(self):
        kwargs = {}
        if self.lang is not None:
            kwargs['lang'] = self.lang.value
        return kwargs

    @lru_cache(maxsize=100)
    def get_param_full_name(self, param: str):
        return eurostat.get_dic(code=self.code, par=param, full=False, **self.get_dic_kwargs())
