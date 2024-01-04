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
    dataclass
)

# from .pyqt_utils import PandasModel


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
    def compute_string_similarity(a, b):
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


class EstatDataset(EstatDatabase):
    """
    TODO: fix this
    Class to represent a specific dataset from Eurostat.
    """
    
    def __init__(self, code):
        self.code = code
        self.pars = eurostat.get_pars(self.code)
        self._units = None
        self._data = None
        self._geo_codes = None
        self._model = None
        self._date_columns = None
        self._params = None
        self._data_start = None
        self._data_end = None
        self._params_abbrs = {}

    # @property
    # def title(self):
    #     return self.toc.loc[self.toc['code'] == self.code, 'title']

    # @property
    # def data_start(self):
    #     if self._data_start is None:
    #         self._data_start = self.date_columns[0]
    #     return self._data_start

    # @property
    # def data_end(self):
    #     if self._data_end is None:
    #         self._data_end = self.date_columns[-1]
    #     return self._data_end
    
    # @property
    # def date_columns(self):
    #     if self._date_columns is None:
    #         self._date_columns = self.data.columns[len(self.params):]
    #     return self._date_columns

    # @property
    # def data(self):
    #     if self._data is None:
    #         self._data = eurostat.get_data_df(code=self.code)
    #         time_period_column = [column for column in self._data.columns
    #                               if column.endswith('TIME_PERIOD')]
    #         if len(time_period_column) == 1:
    #             time_period_column = time_period_column[0]
    #             self._data = self._data.rename(columns={time_period_column:
    #                                                     time_period_column.split('\\')[0]})
    #     return self._data

    # @property
    # def units(self):
    #     if self._units is None:
    #         self._units = pd.DataFrame(eurostat.get_dic(self.code,
    #                                                     'unit',
    #                                                     full=False),
    #                                    columns=['unit_abbr', 'unit_name'])
    #     return self._units
    
    # @property
    # def geo_codes(self):
    #     if self._geo_codes is None:
    #         self._geo_codes = pd.DataFrame(eurostat.get_dic(self.code,
    #                                                         'geo',
    #                                                         full=False),
    #                                        columns=['unit_abbr', 'unit_name'])
    #     return self._geo_codes
    
    # @property
    # def params(self):
    #     if self._params is None:
    #         self._params = eurostat.get_pars(self.code)
    #     return self._params

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

    # def param_names_and_abbrs(self, param):
    #     if param not in self._params_abbrs:
    #         self._params_abbrs[param] = pd.DataFrame(eurostat
    #                                            .get_dic(self.code,
    #                                                     param,
    #                                                     full=False),
    #                                                     columns=[f'{param}_abbr',
    #                                                              f'{param}_name'])
    #     return self._params_abbrs[param]

    # def get_country_code(self, country_name):
    #     geo = self.param_names_and_abbrs('geo')
    #     country_code = geo.loc[geo['geo_name'] == country_name, 'geo_abbr'].values[0]
    #     return country_code


    # def _get_signature(self, fn):
    #     params = inspect.signature(fn).parameters
    #     args = []
    #     kwargs = OrderedDict()
    #     for p in params.values():
    #         if p.default is p.empty:
    #             args.append(getattr(self, p.name))
    #         else:
    #             kwargs[p.name] = getattr(self, p.name)
    #     return args, kwargs

    # def __repr__(self):
    #     self.args, self.kwargs = self._get_signature(self.__init__)
    #     self.repr = self.args
    #     if len(self.kwargs) > 0:
    #         self.repr.extend(
    #             [f'{k}={v}' for k, v in self.kwargs.items()])
    #     return f'EstatDataset({", ".join(self.repr)})'
        
    # def __str__(self):
    #     return self.toc.loc[self.toc['code'] == self.code].to_string()
