from enum import (
    Enum,
    auto
)


class TableOfContentsColumn(Enum):
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


class GeoSectionName(Enum):
    """Enumerates the common fields which describe geographic areas."""
    # NOTE: Feel free to expand this enum
    GEO = 'geo'
    REP_MAR = 'rep_mar'
    PAR_MAR = 'par_mar'
    METROREG = 'metroreg'


class FrequencyType(Enum):
    """Enumerates the frequency types associated with a dataset."""
    ANNUALLY = 'a'
    SEMESTERLY = 's'
    QUARTERLY = 'q'
    MONTHLY = 'm'
    DAILY = 'd'
