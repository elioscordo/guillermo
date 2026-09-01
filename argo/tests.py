from django.test import TransactionTestCase
from argo.models import InstrumentGroup, Instrument, AssetClass
from argo.schemas import SymbolsSchema, SymbolItemSchema


class SymbolsSchemaLiveTest(TransactionTestCase):
    """
    Live integration test for SymbolsSchema using the real IB Gateway/TWS service.
    """

    def setUp(self):
        self.group = InstrumentGroup.objects.create(
            name="US Equities Test",
            code="US_TEST",
            asset_class=AssetClass.EQUITY,
            venue="SMART",
            currency="USD",
        )

    def test_sync_model_live_search(self):
        # 1 valid real symbol and 1 non-existent symbol
        schema = SymbolsSchema(
            symbols=[
                SymbolItemSchema(symbol="AAPL", venue="SMART", currency="USD"),
                SymbolItemSchema(symbol="NONEXISTENT_XYZ_999", venue="SMART", currency="USD"),
            ]
        )

        report = schema.sync_model(self.group)

        # Verify report structure
        self.assertIn("created", report)
        self.assertIn("skipped", report)

        created_symbols = [r["name"] for r in report["created"]]
        skipped_symbols = [s["symbol"] for s in report["skipped"]]

        self.assertIn("AAPL", created_symbols)
        self.assertIn("NONEXISTENT_XYZ_999", skipped_symbols)

        # Verify database state
        instrument = Instrument.objects.filter(symbol="AAPL", venue="SMART").first()
        self.assertIsNotNone(instrument)
        self.assertEqual(instrument.currency, "USD")
        self.assertTrue(hasattr(instrument, "ib_contract"))
        self.assertIn(self.group, instrument.groups.all())
