# coding=utf-8
"""End-to-end workflow integration tests for the eurostat_downloader plugin.

These tests stitch components together (``Database`` -> ``Dataset`` ->
``QgsConverter`` -> ``QgsVectorLayer`` -> GISCO join) using SYNTHETIC data
only. No real Eurostat/GISCO HTTP calls are made: ``Database`` and
``Dataset`` internal fields are populated directly, and the GISCO unit
downloader's ``features`` dict is pre-populated with in-memory features
that bypass the network step entirely.

These tests close the gap left by the existing ``test_ui_*`` files (which
only exercise dialog construction) and ``test_qgs_converter`` (which only
exercises ``dtype_mapper`` in isolation). They are the regression net that
would have caught the original PyQt6 ``QVariant.Type`` crash because they
exercise the full *Select dataset -> Add/Join* user flow rather than the
static type-mapping helper alone.

Covered workflows
-----------------
* ``TestDatasetSelectionWorkflow`` -- bind a synthetic ``Dataset`` to a real
  ``Dialog``, call ``update_model`` and confirm the preview table + the
  join-field combo see the right data.
* ``TestConvertToLayerWorkflow`` -- call ``QgsConverter.from_data_dict``
  with multiple realistic shapes (numeric, all-string -- the exact path
  that hit ``QgsConverter.dtype_mapper`` line 1762 -- and Eurostat-style
  mixed) and assert on the resulting ``QgsVectorLayer``.
* ``TestGISCOJoinWorkflow`` -- build a synthetic GISCO polygon layer in
  memory, pre-populate ``GISCOUnitDownloader.features`` to skip the
  network step, then call ``GISCOHandler.join_data`` and verify a joined
  ``QgsVectorLayer`` is produced with attributes from both sides.
"""

__author__ = 'cuvuliucalexandrei@gmail.com'
__date__ = '2026-05-23'

import unittest
from unittest.mock import MagicMock, patch

from test.utilities import get_qgis_app

QGIS_APP, CANVAS, IFACE, PARENT = get_qgis_app()

from qgis.PyQt import QtCore  # noqa: E402
from qgis.core import (  # noqa: E402
    QgsFeature,
    QgsField,
    QgsGeometry,
    QgsProject,
    QgsVectorLayer,
)

from eurostat_downloader.src.data import (  # noqa: E402
    Database,
    Dataset,
    Unit,
)
from eurostat_downloader.src.enums import Agency, Language  # noqa: E402
from eurostat_downloader.src.eurostat_downloader import (  # noqa: E402
    DataFilterer,
    Dialog,
    EurostatDownloader,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_synthetic_database(code: str = 'TEST_DATA', title: str = 'Test Dataset'):
    """Build a ``Database`` with a single synthetic TOC entry, no I/O."""
    db = Database(lang=Language.ENGLISH)
    db._toc = {
        Agency.EUROSTAT: {
            Language.ENGLISH: [
                {
                    'title': title,
                    'code': code,
                    'type': 'dataset',
                    'level': 0,
                    'last update of data': '2024-01-15',
                    'last table structure change': '2023-12-01',
                    'data start': '2020',
                    'data end': '2023',
                }
            ]
        }
    }
    return db


def _make_synthetic_dataset(
    db: Database,
    code: str = 'TEST_DATA',
    data: dict | None = None,
    params: list[str] | None = None,
) -> Dataset:
    """Construct a ``Dataset`` and directly populate its internal fields.

    Bypasses ``Dataset.initialize_data`` (which would hit the network).
    """
    dataset = Dataset(db=db, code=code, lang=Language.ENGLISH)
    if data is None:
        data = {
            'columns': ['geo', 'sex', '2020', '2021'],
            'data': [
                ['BE', 'T', '100', '110'],
                ['FR', 'T', '200', '210'],
                ['DE', 'T', '300', '310'],
            ],
        }
    if params is None:
        params = ['geo', 'sex']
    dataset._data = data
    dataset._params = params
    return dataset


def _make_synthetic_dialog(
    dataset_data: dict | None = None,
    dataset_params: list[str] | None = None,
    dataset_code: str = 'TEST_DATA',
) -> tuple[EurostatDownloader, Dialog, Database, Dataset]:
    """Build a real ``EurostatDownloader`` + ``Dialog`` with a synthetic
    ``Dataset`` and ``DataFilterer`` already bound. Returns the tuple so
    callers can keep references alive (Qt deletes objects without owners).
    """
    plugin = EurostatDownloader(IFACE)
    dialog = Dialog(plugin)

    db = _make_synthetic_database(code=dataset_code)
    # Replace the dialog's freshly-built database with the synthetic one so
    # all downstream lookups (``dataset.title`` reads from db.toc) work.
    dialog.database = db

    dataset = _make_synthetic_dataset(
        db=db,
        code=dataset_code,
        data=dataset_data,
        params=dataset_params,
    )
    dialog.dataset = dataset
    dialog.filterer = DataFilterer(dataset=dataset)
    return plugin, dialog, db, dataset


# ---------------------------------------------------------------------------
# 1. Dataset selection -> preview model wiring
# ---------------------------------------------------------------------------


class TestDatasetSelectionWorkflow(unittest.TestCase):
    """Dataset -> Dialog -> preview table / join-field combo end-to-end."""

    def setUp(self):
        # Guard against any code path that might pop a modal dialog.
        # Dialog.__init__ never calls exec(), but defensive patching is
        # cheap and prevents a stray dialog from blocking the test process.
        self._exec_patcher = patch(
            'qgis.PyQt.QtWidgets.QDialog.exec', return_value=0
        )
        self._exec_patcher.start()

        (
            self.plugin,
            self.dialog,
            self.db,
            self.dataset,
        ) = _make_synthetic_dialog()

    def tearDown(self):
        self._exec_patcher.stop()
        self.dialog.deleteLater()
        self.dialog = None
        self.plugin = None

    def test_update_model_populates_preview_table(self):
        """``Dialog.update_model`` must wire the synthetic data into the
        ``tableDataset`` view via ``DatasetModel.table_model``."""
        self.dialog.update_model()

        # The dialog stores the composed ``DatasetModel`` on ``self.model``.
        self.assertIsNotNone(self.dialog.model)
        table_model = self.dialog.model.table_model

        # Row count matches the synthetic dataset's 3 rows.
        self.assertEqual(table_model.rowCount(), 3)
        # Column count matches the 4 columns: ['geo', 'sex', '2020', '2021'].
        self.assertEqual(table_model.columnCount(), 4)
        self.assertEqual(table_model._columns, ['geo', 'sex', '2020', '2021'])

        self.assertIsNotNone(self.dialog.ui.tableDataset.model())

    def test_set_table_join_fields_populates_combo(self):
        """The join-field combo is populated from ``dataset.params``."""
        # Mirror the production flow: the DatasetInitializer's
        # ``finished`` signal calls ``set_table_join_fields`` once the
        # dataset is ready. Call it directly with synthetic data.
        self.dialog.set_table_join_fields()

        combo = self.dialog.ui.comboTableJoinField
        items = [combo.itemText(i) for i in range(combo.count())]
        self.assertEqual(items, ['geo', 'sex'])

    def test_get_current_table_join_field_returns_selection(self):
        """The dialog's ``get_current_table_join_field`` helper returns
        whatever the combo currently shows -- needed for downstream join."""
        self.dialog.set_table_join_fields()
        # Default to 'geo' (the first param, also matches GeoSectionName).
        self.dialog.set_table_join_field_default()
        self.assertEqual(self.dialog.get_current_table_join_field(), 'geo')

    def test_preview_model_reads_filtered_data(self):
        """When ``update_model`` runs, the filterer's ``apply_filters``
        result is what feeds the table model -- so applying a row filter
        on ``geo`` must shrink the visible rows."""
        # Limit to just Belgium.
        self.dialog.filterer.add_row_filters({'geo': ['BE']})
        self.dialog.update_model()

        table_model = self.dialog.model.table_model
        self.assertEqual(table_model.rowCount(), 1)
        # Column count unchanged.
        self.assertEqual(table_model.columnCount(), 4)


# ---------------------------------------------------------------------------
# 2. QgsConverter.from_data_dict -> QgsVectorLayer
# ---------------------------------------------------------------------------


class TestConvertToLayerWorkflow(unittest.TestCase):
    """``QgsConverter.from_data_dict`` for the shapes the plugin sees."""

    def setUp(self):
        self._exec_patcher = patch(
            'qgis.PyQt.QtWidgets.QDialog.exec', return_value=0
        )
        self._exec_patcher.start()

        (
            self.plugin,
            self.dialog,
            self.db,
            self.dataset,
        ) = _make_synthetic_dialog()

    def tearDown(self):
        self._exec_patcher.stop()
        self.dialog.deleteLater()
        self.dialog = None
        self.plugin = None

    def _field_types(self, layer: QgsVectorLayer) -> list:
        return [layer.fields().at(i).type() for i in range(layer.fields().count())]

    def test_numeric_data_produces_int_and_double_fields(self):
        """Int + float columns get inferred as Int + Double respectively."""
        columns = ['geo_id', 'value']
        rows = [[1, 2.5], [3, 4.0], [5, 6.0]]

        layer = self.dialog.converter.from_data_dict(rows, columns)

        self.assertIsInstance(layer, QgsVectorLayer)
        self.assertEqual(layer.fields().count(), 2)
        self.assertEqual(layer.featureCount(), 3)

        types = self._field_types(layer)
        # Per dtype_mapper: ints -> QMetaType.Int, floats -> QMetaType.Double.
        self.assertEqual(types[0], QtCore.QMetaType.Type.Int)
        self.assertEqual(types[1], QtCore.QMetaType.Type.Double)

    def test_all_string_data_crash_repro_produces_qstring_fields(self):
        """Regression: all-string columns must produce ``QString`` fields.

        This is the exact path that hit ``QgsConverter.dtype_mapper``'s
        line-1762 ``ValueError`` branch under the old PyQt5 ``QVariant.Type``
        form. Under PyQt6 with ``QMetaType.Type.QString`` it must round-trip
        cleanly and build a real vector layer.
        """
        columns = ['code', 'label']
        rows = [['A', 'X'], ['B', 'Y'], ['C', 'Z']]

        layer = self.dialog.converter.from_data_dict(rows, columns)

        self.assertIsInstance(layer, QgsVectorLayer)
        self.assertEqual(layer.fields().count(), 2)
        self.assertEqual(layer.featureCount(), 3)

        types = self._field_types(layer)
        self.assertEqual(types[0], QtCore.QMetaType.Type.QString)
        self.assertEqual(types[1], QtCore.QMetaType.Type.QString)

        # Values round-trip.
        feats = list(layer.getFeatures())
        self.assertEqual(feats[0].attributes(), ['A', 'X'])
        self.assertEqual(feats[2].attributes(), ['C', 'Z'])

    def test_eurostat_style_mixed_columns(self):
        """Eurostat data shape: geo codes (str) + sex codes (str) + yearly
        values (numeric-as-string -> inferred as Int by ``dtype_mapper``)."""
        columns = ['geo', 'sex', '2020', '2021']
        rows = [
            ['BE', 'T', '100', '110'],
            ['FR', 'T', '200', '210'],
            ['DE', 'T', '300', '310'],
        ]

        layer = self.dialog.converter.from_data_dict(rows, columns)

        self.assertIsInstance(layer, QgsVectorLayer)
        self.assertEqual(layer.fields().count(), len(columns))
        self.assertEqual(layer.featureCount(), len(rows))

        types = self._field_types(layer)
        # geo + sex are non-numeric strings -> QString.
        self.assertEqual(types[0], QtCore.QMetaType.Type.QString)
        self.assertEqual(types[1], QtCore.QMetaType.Type.QString)
        # Year columns hold integer-looking strings -> Int per dtype_mapper.
        self.assertEqual(types[2], QtCore.QMetaType.Type.Int)
        self.assertEqual(types[3], QtCore.QMetaType.Type.Int)

    def test_layer_name_matches_dataset_code(self):
        """``from_data_dict`` names the layer after the bound dataset code
        (used in ``Exporter.add_table`` when registering the layer in QGIS)."""
        layer = self.dialog.converter.from_data_dict(
            [['1', '2']], ['a', 'b']
        )
        # ``from_data_dict`` itself sets the layer source name to
        # ``self.base.dataset.code`` via the QgsVectorLayer constructor.
        self.assertEqual(layer.name(), self.dataset.code)


# ---------------------------------------------------------------------------
# 3. GISCO join workflow
# ---------------------------------------------------------------------------


class TestGISCOJoinWorkflow(unittest.TestCase):
    """``GISCOHandler.join_data`` end-to-end with synthetic features."""

    def setUp(self):
        self._exec_patcher = patch(
            'qgis.PyQt.QtWidgets.QDialog.exec', return_value=0
        )
        self._exec_patcher.start()

        # Eurostat dataset bound to the dialog -- this is the *attribute*
        # side of the join. Geo codes BE/FR/DE align with the synthetic
        # GISCO polygons built below.
        eurostat_data = {
            'columns': ['geo', '2020'],
            'data': [
                ['BE', '100'],
                ['FR', '200'],
                ['DE', '300'],
            ],
        }
        (
            self.plugin,
            self.dialog,
            self.db,
            self.dataset,
        ) = _make_synthetic_dialog(
            dataset_data=eurostat_data,
            dataset_params=['geo'],
        )

        # Mirror the production flow so the dialog has a model + the
        # filterer's column ordering is correct. ``join_data`` reads
        # ``self.base.converter.table`` which reaches into ``self.base.model``.
        self.dialog.update_model()
        self.dialog.set_table_join_fields()
        self.dialog.set_table_join_field_default()

    def tearDown(self):
        self._exec_patcher.stop()
        # Clear project state to avoid leaking layers between tests.
        instance = QgsProject.instance()
        if instance is not None:
            instance.removeAllMapLayers()
        self.dialog.deleteLater()
        self.dialog = None
        self.plugin = None

    def _build_synthetic_features(self) -> dict:
        """Build a dict[Unit, list[QgsFeature]] that bypasses the network.

        ``GISCOHandler.join_data`` calls
        ``itertools.chain.from_iterable(self.unit_downloader.features.values())``
        and then ``layer_from_features(features, crs=...)``. Each feature
        must carry a ``_UNIT_ID`` attribute (that's the JOIN field on the
        GISCO side, see ``join_data``'s ``processing.run`` call).
        """
        # Build a real polygon vector layer to serve as the source of
        # fields + geometry; we then lift its features out into the dict.
        gisco_layer = QgsVectorLayer(
            'Polygon?crs=epsg:4326', 'gisco_test', 'memory'
        )
        provider = gisco_layer.dataProvider()
        provider.addAttributes(
            [
                QgsField('NUTS_ID', QtCore.QMetaType.Type.QString),
                QgsField('_UNIT_ID', QtCore.QMetaType.Type.QString),
            ]
        )
        gisco_layer.updateFields()
        for code in ['BE', 'FR', 'DE']:
            feat = QgsFeature(gisco_layer.fields())
            feat.setAttributes([code, code])  # _UNIT_ID == code for the join
            feat.setGeometry(
                QgsGeometry.fromWkt(
                    'POLYGON((0 0, 1 0, 1 1, 0 1, 0 0))'
                )
            )
            provider.addFeature(feat)

        # Keep gisco_layer alive on self so its fields() backing storage
        # stays valid for the features (Qt/QGIS object lifetimes are
        # subtle in test contexts).
        self._gisco_source_layer = gisco_layer

        # Pack into the {Unit: [QgsFeature, ...]} shape join_data expects.
        unit = Unit(
            id='nuts',
            spatial_type='RG',
            scale='20M',
            projection='4326',
            year='2020',
        )
        return {unit: list(gisco_layer.getFeatures())}

    def test_join_data_produces_layer_with_joined_attributes(self):
        """End-to-end: synthetic features + bound dataset + ``join_data``
        must yield a joined ``QgsVectorLayer`` with attributes from both
        sides and a feature for each matching geo code."""
        # Pre-populate the unit_downloader so the network-bound branch in
        # ``join_handler`` is bypassed and ``join_data`` is called against
        # ready-made features.
        self.dialog.gisco_handler.unit_downloader = MagicMock()
        self.dialog.gisco_handler.unit_downloader.features = (
            self._build_synthetic_features()
        )

        # ``join_data`` reads the projection from the GISCO projection
        # combo. Force a valid EPSG so ``layer_from_features`` succeeds.
        self.dialog.ui.comboBoxGISCOProjection.clear()
        self.dialog.ui.comboBoxGISCOProjection.addItem('4326')
        self.dialog.ui.comboBoxGISCOProjection.setCurrentIndex(0)

        # The Eurostat-side join field defaults to 'geo' (a GeoSectionName).
        self.assertEqual(
            self.dialog.get_current_table_join_field(), 'geo'
        )

        # Run the join.
        self.dialog.gisco_handler.join_data()

        # ``join_data`` registers the result on the global QgsProject. We
        # find it by the dataset code name.
        layers = QgsProject.instance().mapLayersByName(self.dataset.code)
        self.assertTrue(
            layers,
            'join_data should have added a layer named after the dataset code',
        )
        joined = layers[0]
        self.assertIsInstance(joined, QgsVectorLayer)

        # Three matching geo codes (BE, FR, DE) -> three joined features.
        self.assertEqual(joined.featureCount(), 3)

        # Attributes from BOTH sides must be present. GISCO side
        # contributes 'NUTS_ID' + '_UNIT_ID'; Eurostat side contributes
        # 'geo' + '2020' (the latter may be suffixed by the join algorithm).
        field_names = [f.name() for f in joined.fields()]
        self.assertIn('NUTS_ID', field_names)
        self.assertIn('_UNIT_ID', field_names)
        # Eurostat columns may or may not be renamed depending on the
        # processing algorithm; assert at least one Eurostat-side column
        # is present.
        eurostat_columns_present = [
            n for n in field_names if n == 'geo' or n.startswith('geo')
        ] + [n for n in field_names if n == '2020' or n.startswith('2020')]
        self.assertTrue(
            eurostat_columns_present,
            f'Joined layer is missing Eurostat-side columns; got {field_names}',
        )

    def test_join_data_with_no_features_returns_none(self):
        """When ``unit_downloader.features`` is empty, ``join_data`` is a
        no-op (returns None) -- documented early-return contract."""
        self.dialog.gisco_handler.unit_downloader = MagicMock()
        self.dialog.gisco_handler.unit_downloader.features = {}

        result = self.dialog.gisco_handler.join_data()
        self.assertIsNone(result)


if __name__ == '__main__':
    suite = unittest.TestLoader().loadTestsFromModule(__import__(__name__))
    runner = unittest.TextTestRunner(verbosity=2)
    runner.run(suite)
