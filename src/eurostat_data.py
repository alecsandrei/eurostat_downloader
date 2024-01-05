import inspect
from collections import OrderedDict
from functools import (
    cached_property,
    lru_cache
)
from difflib import SequenceMatcher

import eurostat
import pandas as pd
from dataclasses import (
    dataclass,
    field
)

# from .pyqt_utils import PandasModel


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
    _units = None
    _data = None
    _geo_codes = None
    _model = None
    _date_columns = None
    _params = None
    _data_start = None
    _data_end = None
    _params_abbrs = {}

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
    def units(self):
        return pd.DataFrame(
            eurostat.get_dic(self.code, 'unit', full=False), columns=['unit_abbr', 'unit_name']
        )
    
    @cached_property
    def geo_codes(self):
        return (
            pd.DataFrame(eurostat.get_dic(self.code, 'geo', full=False), columns=['unit_abbr', 'unit_name'])
        )
    
    @cached_property
    def params(self):
        return eurostat.get_pars(self.code)

    # @property
    # def model(self):
    #     return self._model
    
    # @model.setter
    # def model(self, model: PandasModel):
    #     self._model = model

    # @property
    # def model_data(self):
    #     if self.model is None:
    #         return self.data
    #     else:
    #         return self.model._data

    # @property
    # def model_data_date_columns(self):
    #     return self.model_data.drop(columns=self.params).columns.to_list()

    def param_names_and_abbrs(self, param):
        if param not in self._params_abbrs:
            self._params_abbrs[param] = pd.DataFrame(eurostat
                                               .get_dic(self.code,
                                                        param,
                                                        full=False),
                                                        columns=[f'{param}_abbr',
                                                                 f'{param}_name'])
        return self._params_abbrs[param]

    def get_country_code(self, country_name):
        geo = self.param_names_and_abbrs('geo')
        country_code = geo.loc[geo['geo_name'] == country_name, 'geo_abbr'].values[0]
        return country_code
