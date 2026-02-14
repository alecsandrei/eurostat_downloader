# Eurostat Downloader QGIS Plugin - AI Assistant Guide

## Project Overview

This is a QGIS plugin that downloads Eurostat datasets and GISCO geospatial data via APIs, allowing users to join statistical data with vector layers in QGIS. The plugin handles dependency management, provides a custom Qt-based UI, and supports multiple European statistical agencies.

## Build & Package

```bash
# Package the plugin for distribution
qgis-plugin-ci package 0.5.0

# Package with uncommitted changes allowed
qgis-plugin-ci package 0.5.0 -c
```

The package task creates `eurostat_downloader.0.5.0.zip` in the parent directory, excluding development files (.vscode, .git, caches, tests, etc.).

## Testing

```bash
# Run all tests with the test runner
python test/test_runner.py

# Run a specific test module
python -m pytest test/test_data.py

# Run a single test
python -m pytest test/test_data.py::TestDatabase::test_database_initialization
```

Tests require QGIS environment initialization via `test.utilities.get_qgis_app()`.

## Code Quality

```bash
# Lint with ruff
ruff check .

# Format with ruff
ruff format .

# Type check with mypy
mypy .
```

**Ruff configuration:**
- Line length: 80 characters
- Single quotes enforced
- All files must start with `from __future__ import annotations`
- Minimal select rules (E4, E7, E9, F)

## Architecture

### Plugin Entry Point

- `__init__.py`: QGIS plugin initialization
  - Returns `EurostatDownloader` class instance

### Core Components

**`src/eurostat_downloader.py`**: Main plugin class
- Manages QGIS interface integration (menu, toolbar)
- Implements two-tab UI: Layer (Eurostat datasets) and GISCO (geospatial data)
- Handles dataset selection, filtering, and joining with vector layers
- Uses Qt signals/slots for async network requests

**`src/data.py`**: Data models and API interaction
- `Database`: Manages table of contents (TOC) from multiple agencies (EUROSTAT, COMEXT, COMP, EMPL, GROW)
- `Dataset`: Represents individual Eurostat datasets with filtering capabilities
- `GISCO`: Handles geospatial datasets (NUTS regions, Urban Audit, etc.)
- `Units`: Collection of GISCO units with metadata
- Uses concurrent.futures for parallel API calls
- Caches TOC locally by date

**`src/fetch.py`**: Low-level API communication
- Defines API endpoints and SDMX XML namespaces
- Implements direct HTTP requests using QGIS network manager
- Handles different agency base URLs

**`src/modules.py`**: (Legacy) Dependency management
- Previously used for detecting missing Python packages
- Now largely unused as plugin has no external dependencies
- Provides UI to install packages via pip
- Manages `extlibs/` installation folder

**`src/settings.py`**: Global configuration
- Proxy settings
- SSL verification toggle
- Agency selection
- Persistent QSettings storage

**`src/utils.py`**: UI utilities
- `CheckableComboBox`: Multi-select dropdown
- `QComboboxCompleter`: Autocomplete for comboboxes
- Helper functions for QGIS layers and table manipulation

**`src/enums.py`**: Enumerations for languages, agencies, connection status, etc.

### UI Architecture

- `.ui` files define Qt Designer layouts (not directly loaded by code)
- Compiled to Python modules via `ui/compile.sh` (uses `pyuic5`)
- Python UI modules imported from `src/ui/`

### Resource Management

- `resources.qrc`: Qt resource file listing assets (icons, images)
- `resources.py`: Compiled resource module (generated from .qrc)

## Key Conventions

### Import Pattern
Every Python file starts with:
```python
from __future__ import annotations
```

### Dependency Installation
- External packages installed to `extlibs/` folder (platform-specific)
- Path added via `site.addsitedir()` not `sys.path.insert()` to handle `.pth` files
- User prompted on first run if dependencies missing

### QGIS Integration
- Plugin uses QGIS network manager (`QgsNetworkAccessManager`) for all HTTP requests
- Temporary layers created for preview, must be exported to persist joined data
- Vector layer joins use `QgsVectorLayerJoinInfo`

### Async Operations
- Table of contents fetching parallelized across agencies/languages
- Qt signals used for non-blocking UI during API calls
- Network requests use Qt's async request/reply pattern

### Testing
- Tests require QGIS app initialization before imports
- Mock external API calls in unit tests
- Integration tests use actual QGIS environment

### Language Support
- Multi-language UI via Qt translation files (`i18n/`)
- Eurostat dataset metadata available in multiple languages
- Language enum maps to API language codes

## External Dependencies

**Runtime (required):**
- QGIS 3.00+ with PyQt5

**Development:**
- `paver`: Build and packaging tool
- `ruff`: Linting and formatting
- `mypy`: Type checking
- `unittest`: Test runner (built-in to Python)

## Plugin Distribution

The plugin is distributed via:
1. QGIS plugin repository (may be marked experimental)
2. Manual installation from GitHub releases (eurostat_downloader.zip)

No external dependencies are required - the plugin works out of the box with QGIS 3.00+.
