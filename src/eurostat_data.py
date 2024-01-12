from typing import Union
from functools import (
    cached_property,
    lru_cache
)
from difflib import SequenceMatcher
from dataclasses import (
    dataclass,
    field
)

import eurostat
import pandas as pd



@dataclass
class EstatDatabase:

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


@dataclass
class EstatDataset(EstatDatabase):
    """
    TODO: fix this
    Class to represent a specific dataset from Eurostat.
    """
    database: EstatDatabase
    code: str
    pars: list[str] = field(init=False)

    @cached_property
    def title(self):
        return self.toc.loc[self.toc['code'] == self.code, 'title']

    # @cached_property
    # def data_start(self):
    #     return self.date_columns[0]

    # @cached_property
    # def data_end(self):
    #     return self.date_columns[-1]
    
    # @cached_property
    # def date_columns(self):
    #     return self.data.columns[len(self.params):]

    @cached_property
    def df(self) -> pd.DataFrame:
        return eurostat.get_data_df(code=self.code)
    
    @cached_property
    def params(self):
        return eurostat.get_pars(self.code)
