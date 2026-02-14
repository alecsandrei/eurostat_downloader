from __future__ import annotations

import os
from pathlib import Path

__all__ = ['DEBUG', 'PACKAGE_DIR']

DEBUG = os.getenv('EUROSTAT_PLUGIN_DEBUG', '0') == '1'
PACKAGE_DIR = Path(__file__).parent
