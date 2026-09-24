import datetime
import math
import random
from typing import List, Optional, Tuple
from nautilus_trader.model.data import Bar, BarType
from nautilus_trader.model.enums import AggregationSource, BarAggregation, PriceType
from nautilus_trader.model.identifiers import InstrumentId
from nautilus_trader.model.objects import Price, Quantity
from nautilus_trader.persistence.catalog import ParquetDataCatalog


class BacktestDataLoader:
    """
    Adapter loading historical bar datasets for Nautilus Trader backtesting.
    Supports ParquetDataCatalog, on-demand download, and fallback market generation.
    """

    def __init__(self, catalog_path: Optional[str] = None):
        if not catalog_path:
            import os
            from django.conf import settings
            catalog_path = getattr(settings, "HISTORICAL_ROOT", None) or os.path.join(getattr(settings, "BASE_DIR", "."), "historical_data")
        self.catalog_path = str(catalog_path)

    def load_bars(
        self,
        instrument_id: InstrumentId,
        bar_type: BarType,
        start: datetime.datetime,
        end: datetime.datetime,
    ) -> List[Bar]:
        """Loads bars from catalog or generates fallback continuous data series."""
        bars, _ = self.load_or_fetch_bars(instrument_id, bar_type, start, end)
        return bars

    def load_or_fetch_bars(
        self,
        instrument_id: InstrumentId,
        bar_type: BarType,
        start: datetime.datetime,
        end: datetime.datetime,
        instrument_obj=None,
    ) -> Tuple[List[Bar], str]:
        """
        Loads bars with fallback chain: local catalog -> IB Gateway download -> synthetic generation.
        Returns a tuple of (bars, source_name).
        """
        if getattr(bar_type, 'aggregation_source', None) != AggregationSource.EXTERNAL:
            bar_type = BarType.from_str(str(bar_type).replace("-INTERNAL", "-EXTERNAL"))

        catalog_bars = self._load_from_catalog(bar_type, start, end)
        if catalog_bars:
            return catalog_bars, "catalog"

        if instrument_obj:
            ib_bars = self._fetch_from_ib(instrument_obj, bar_type, start, end)
            if ib_bars:
                self.write_bars(ib_bars)
                return ib_bars, "ib_gateway"

        synthetic_bars = self._generate_synthetic_bars(instrument_id, bar_type, start, end)
        self.write_bars(synthetic_bars)
        return synthetic_bars, "synthetic"

    def write_bars(self, bars: List[Bar]) -> None:
        """Persists historical bars into the ParquetDataCatalog."""
        if not bars:
            return
        try:
            catalog = ParquetDataCatalog(self.catalog_path)
            catalog.write_data(bars)
        except Exception:
            pass

    def _fetch_from_ib(
        self,
        instrument_obj,
        bar_type: BarType,
        start: datetime.datetime,
        end: datetime.datetime,
    ) -> Optional[List[Bar]]:
        """Attempts on-demand historical bar extraction from IB Gateway via ib_async."""
        try:
            from ib_async import IB, Stock, Forex
            from django.conf import settings
            host = getattr(settings, "IB_HOST", "127.0.0.1")
            port = getattr(settings, "IB_PORT", 4002)
            ib = IB()
            ib.connect(host=host, port=port, clientId=96, timeout=3.0)
            if not ib.isConnected():
                return None

            sec_type = getattr(instrument_obj, "sec_type", "STK")
            symbol = instrument_obj.symbol
            currency = instrument_obj.currency or "USD"
            exchange = instrument_obj.venue or "SMART"

            contract = Forex(symbol) if sec_type == "CASH" else Stock(symbol, exchange, currency)
            duration_days = max(1, (end - start).days + 1)
            duration_str = f"{duration_days} D" if duration_days <= 365 else f"{max(1, duration_days // 365)} Y"

            ib_data = ib.reqHistoricalData(
                contract,
                endDateTime=end,
                durationStr=duration_str,
                barSizeSetting="1 min",
                whatToShow="MIDPOINT" if sec_type == "CASH" else "TRADES",
                useRTH=True,
                formatDate=1,
            )
            ib.disconnect()

            if not ib_data:
                return None

            nautilus_bars: List[Bar] = []
            for b in ib_data:
                ts_ns = int(b.date.timestamp() * 1_000_000_000)
                nautilus_bars.append(
                    Bar(
                        bar_type=bar_type,
                        open=Price(b.open, precision=2),
                        high=Price(b.high, precision=2),
                        low=Price(b.low, precision=2),
                        close=Price(b.close, precision=2),
                        volume=Quantity(max(1, int(b.volume or 1)), precision=0),
                        ts_event=ts_ns,
                        ts_init=ts_ns,
                    )
                )
            return nautilus_bars
        except Exception:
            return None

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
            if not bars and "-EXTERNAL" in str(bar_type):
                alt_bt = BarType.from_str(str(bar_type).replace("-EXTERNAL", "-INTERNAL"))
                bars = catalog.bars(bar_type=alt_bt, start=start, end=end)
            return list(bars) if bars else None
        except Exception:
            return None

    def _get_bar_step(self, bar_type: BarType) -> datetime.timedelta:
        """Determines the timedelta increment for a given BarType."""
        try:
            spec = getattr(bar_type, "spec", getattr(bar_type, "bar_spec", None))
            if spec:
                step_val = getattr(spec, "step", 1) or 1
                agg_str = str(getattr(spec, "aggregation", "")).upper()
                if "SECOND" in agg_str:
                    return datetime.timedelta(seconds=step_val)
                if "MINUTE" in agg_str:
                    return datetime.timedelta(minutes=step_val)
                if "HOUR" in agg_str:
                    return datetime.timedelta(hours=step_val)
                if "DAY" in agg_str:
                    return datetime.timedelta(days=step_val)
                if "WEEK" in agg_str:
                    return datetime.timedelta(weeks=step_val)
        except Exception:
            pass

        bar_str = str(bar_type).upper()
        if "HOUR" in bar_str:
            return datetime.timedelta(hours=1)
        if "DAY" in bar_str:
            return datetime.timedelta(days=1)
        if "SECOND" in bar_str:
            return datetime.timedelta(seconds=1)
        return datetime.timedelta(minutes=1)

    def _generate_synthetic_bars(
        self,
        instrument_id: InstrumentId,
        bar_type: BarType,
        start: datetime.datetime,
        end: datetime.datetime,
        initial_price: float = 100.0,
        volatility: float = 0.20,
        drift: float = 0.05,
    ) -> List[Bar]:
        """Generates realistic Geometric Brownian Motion bar data for testing and simulation."""
        bars: List[Bar] = []
        current_dt = start
        current_price = max(1.0, float(initial_price))
        step = self._get_bar_step(bar_type)
        rng = random.Random(42)  # Deterministic seed for reproducible simulation

        # Scale annual volatility and drift to the discrete time step dt
        seconds_in_year = 365.25 * 86400.0
        dt = max(1.0, step.total_seconds()) / seconds_in_year
        step_drift = (drift - 0.5 * (volatility ** 2)) * dt
        step_vol = volatility * math.sqrt(dt)

        while current_dt <= end:
            growth = math.exp(step_drift + step_vol * rng.gauss(0, 1))
            next_close = max(0.01, min(current_price * growth, 1_000_000.0))

            spread = step_vol * current_price * 0.5
            high_diff = abs(rng.gauss(0, spread))
            low_diff = abs(rng.gauss(0, spread))
            high = min(1_000_000.0, max(current_price, next_close) + high_diff)
            low = max(0.01, min(current_price, next_close) - low_diff)

            ts_ns = int(current_dt.timestamp() * 1_000_000_000)
            bar = Bar(
                bar_type=bar_type,
                open=Price(round(current_price, 2), precision=2),
                high=Price(round(high, 2), precision=2),
                low=Price(round(low, 2), precision=2),
                close=Price(round(next_close, 2), precision=2),
                volume=Quantity(rng.randint(500, 5000), precision=0),
                ts_event=ts_ns,
                ts_init=ts_ns,
            )
            bars.append(bar)
            current_price = next_close
            current_dt += step

        return bars
