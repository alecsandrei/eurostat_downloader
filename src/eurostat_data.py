from typing import Union
from functools import (
    cached_property,
    lru_cache
)
from difflib import SequenceMatcher
from dataclasses import dataclass

import eurostat
import pandas as pd


@dataclass(frozen=True, eq=True)
class Database:

    @cached_property
    def toc(self):
        return eurostat.get_toc_df()
    
    @cached_property
    def units(self):
        return eurostat.get_dic(self.toc.iloc[0].code, 'unit')

    @property
    def toc_titles(self):
        return self.toc['title']
    
    @property
    def toc_size(self):
        return self.toc.shape[0]
    
    @staticmethod
    def compute_string_similarity(a: str, b: str):
        """Computes string similarity between two strings."""
        return SequenceMatcher(None, a, b).ratio()

    def get_subset(self, keyword: str):
        """Creates a subset of the toc. Uses SequenceMatcher to sort the results."""
        if not keyword:
            return self.toc
        keyword = keyword.lower()
        self.toc['match_ratio_title'] = self.toc['title'].apply(lambda x: self.compute_string_similarity(keyword, x.lower()))
        self.toc['match_ratio_code'] = self.toc['code'].apply(lambda x: self.compute_string_similarity(keyword, x.lower()))
        self.toc['match_ratio'] = self.toc['match_ratio_title'] + self.toc['match_ratio_code']
        subset = self.toc.loc[self.toc['match_ratio'] > 0.5].sort_values(by='match_ratio', ascending=False)
        self.toc.drop(columns=['match_ratio_title', 'match_ratio_code', 'match_ratio'], inplace=True)
        return subset

    def get_titles(self, subset: Union[None, pd.DataFrame] = None):
        if subset is None:
            subset = self.toc
        return subset['title']
    
    def get_codes(self, subset: Union[None, pd.DataFrame, pd.Series] = None):
        if subset is None:
            subset = self.toc
        return subset['code']


@dataclass(frozen=True, eq=True)
class Dataset:
    """Class to represent a specific dataset from Eurostat."""
    db: Database
    code: str

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
        return self.db.toc.loc[self.db.toc['code'] == self.code, 'title']
    
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

    @lru_cache(maxsize=100)
    def get_param_full_name(self, param: str):
        return eurostat.get_dic(code=self.code, par=param, full=False)
