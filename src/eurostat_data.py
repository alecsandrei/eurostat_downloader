from functools import (
    cached_property,
    lru_cache
)
from difflib import SequenceMatcher

import eurostat
import pandas as pd
from pandas import DataFrame
from dataclasses import (
    dataclass,
    field
)

from utils import PyQtUtils



@dataclass(slots=False)
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

    @lru_cache(maxsize=16)
    def subset_database(self, keyword: str):
        """Creates a subset of the toc. Uses SequenceMatcher to sort the results."""
        keyword = keyword.lower()
        self.toc['match_ratio_title'] = self.toc['title'].apply(lambda x: self.compute_string_similarity(keyword, x.lower()))
        self.toc['match_ratio_code'] = self.toc['code'].apply(lambda x: self.compute_string_similarity(keyword, x.lower()))
        self.toc['match_ratio'] = self.toc['match_ratio_title'] + self.toc['match_ratio_code']
        current_subset = (self.toc.loc[self.toc['match_ratio'] > 0.5]
                          .sort_values(by='match_ratio', ascending=False))
        self.toc.drop(columns=['match_ratio_title','match_ratio_code', 'match_ratio'], inplace=True)
        current_subset.drop_duplicates(inplace=True)
        return current_subset


@dataclass(slots=False)
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

    @cached_property
    def data_start(self):
        return self.date_columns[0]

    @cached_property
    def data_end(self):
        return self.date_columns[-1]
    
    @cached_property
    def date_columns(self):
        return self.data.columns[len(self.params):]

    @cached_property
    def data(self):
        data = eurostat.get_data_df(code=self.code)
        assert data is not None, 'data is none'
        time_period_column = [column for column in data.columns if column.endswith('TIME_PERIOD')]
        if len(time_period_column) == 1:
            time_period_column = time_period_column[0]
            data = data.rename(columns={time_period_column: time_period_column.split('\\')[0]})
        return data
    
    @cached_property
    def params(self):
        return eurostat.get_pars(self.code)


@dataclass
class EstatDatasetModel:
    estat_dataset: EstatDataset
    df: DataFrame
    
    @cached_property
    def model(self) -> PyQtUtils.PandasModel:
        return PyQtUtils.PandasModel(data=self.df)
