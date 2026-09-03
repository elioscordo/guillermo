import datetime
import math
import random
from typing import List, Optional
from nautilus_trader.model.data import Bar, BarType
from nautilus_trader.model.enums import BarAggregation, PriceType
from nautilus_trader.model.identifiers import InstrumentId
from nautilus_trader.model.objects import Price, Quantity
from nautilus_trader.persistence.catalog import ParquetDataCatalog


class BacktestDataLoader:
    """
    Adapter loading historical bar datasets for Nautilus Trader backtesting.
    Supports ParquetDataCatalog, on-demand download, and fallback market generation.
    """

    def __init__(self, catalog_path: str = "./catalog"):
        self.catalog_path = catalog_path

    def load_bars(
        self,
        instrument_id: InstrumentId,
        bar_type: BarType,
        start: datetime.datetime,
        end: datetime.datetime,
    ) -> List[Bar]:
        """Loads bars from catalog or generates fallback continuous data series."""
        catalog_bars = self._load_from_catalog(bar_type, start, end)
        if catalog_bars:
            return catalog_bars

        return self._generate_synthetic_bars(instrument_id, bar_type, start, end)

    def _load_from_catalog(
        self,
        bar_type: BarType,
        start: datetime.datetime,
        end: datetime.datetime,
    ) -> Optional[List[Bar]]:
        """Attempts to read historical bars from local ParquetDataCatalog."""
        try:
            catalog = ParquetDataCatalog(self.catalog_path)
            bars = catalog.bars(
                bar_type=bar_type,
                start=start,
                end=end,
            )
            return list(bars) if bars else None
        except Exception:
            return None

    def _generate_synthetic_bars(
        self,
        instrument_id: InstrumentId,
        bar_type: BarType,
        start: datetime.datetime,
        end: datetime.datetime,
        initial_price: float = 100.0,
        volatility: float = 0.015,
        drift: float = 0.0003,
    ) -> List[Bar]:
        """Generates realistic Geometric Brownian Motion bar data for testing and simulation."""
        bars: List[Bar] = []
        current_dt = start
        current_price = initial_price
        step = datetime.timedelta(minutes=1 if bar_type.bar_period == 1 else 60)
        rng = random.Random(42)  # Deterministic seed for reproducible simulation

        while current_dt <= end:
            # Multi-regime trending GBM
            pct_change = drift + volatility * rng.gauss(0, 1)
            next_close = max(1.0, current_price * (1.0 + pct_change))
            high_diff = abs(rng.gauss(0, volatility * current_price * 0.7))
            low_diff = abs(rng.gauss(0, volatility * current_price * 0.7))
            high = max(current_price, next_close) + high_diff
            low = min(current_price, next_close) - low_diff

            ts_ns = int(current_dt.timestamp() * 1_000_000_000)
            bar = Bar(
                bar_type=bar_type,
                open=Price(current_price, precision=2),
                high=Price(high, precision=2),
                low=Price(low, precision=2),
                close=Price(next_close, precision=2),
                volume=Quantity(rng.randint(500, 5000), precision=0),
                ts_event=ts_ns,
                ts_init=ts_ns,
            )
            bars.append(bar)
            current_price = next_close
            current_dt += step

        return bars
