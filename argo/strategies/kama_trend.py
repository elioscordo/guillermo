"""
Kaufman Adaptive Moving Average (KAMA) Trend-Following Strategy
==============================================================
Dynamically adapts smoothing speed based on market efficiency (ER) to eliminate whipsaws
and capture clean trends, augmented with multi-factor filters and statistical risk forecasting.

Optimization & Tuning Tips:
---------------------------
1. `er_period`:
   - 10 bars is standard for calculating price change vs path noise.
   - 14-20 bars produces more conservative efficiency measurements for high-volatility assets.
2. `fast_period` and `slow_period`:
   - fast_period=2, slow_period=30 gives optimal responsiveness when trending while staying flat during chop.
3. `min_efficiency`:
   - Increase to 0.35-0.45 to trade only during high-conviction momentum runs.
"""

from typing import List, Optional
from nautilus_trader.trading.config import StrategyConfig
from nautilus_trader.model.data import Bar, BarType
from nautilus_trader.model.enums import OrderSide, TimeInForce
from nautilus_trader.trading.strategy import Strategy as NautilusStrategy

from argo.strategies.base import ArgoBaseStrategy
from argo.strategies.filters import (
    FilterPipeline,
    ADXTrendStrengthFilter,
    ATRVolatilityRegimeFilter,
    EfficiencyRatioNoiseFilter,
)
from argo.strategies.forecaster import PositionRiskForecaster, PositionRiskMetrics


class KaufmanAdaptiveTrendConfig(StrategyConfig, frozen=True):
    """
    Configuration parameters for KaufmanAdaptiveTrendStrategy.

    Attributes:
        instrument_id: Nautilus InstrumentId string (e.g. 'EUR/USD.IB').
        bar_type: Bar aggregation string (e.g. 'EUR/USD.IB-1-MINUTE-MID-EXTERNAL').
        er_period: Lookback window for Efficiency Ratio calculation (default: 10).
        fast_period: Fastest EMA smoothing period when market is trending (default: 2).
        slow_period: Slowest EMA smoothing period when market is noisy (default: 30).
        trade_size: Position order quantity in base units or contracts (default: 100.0).
        min_efficiency: Minimum Efficiency Ratio required to permit entry (default: 0.30).
        min_adx: Minimum ADX trend strength threshold (default: 20.0).
    """
    instrument_id: str
    bar_type: str
    er_period: int = 10
    fast_period: int = 2
    slow_period: int = 30
    trade_size: float = 100.0
    min_efficiency: float = 0.30
    min_adx: float = 20.0


class KaufmanAdaptiveTrendStrategy(ArgoBaseStrategy):
    """
    Kaufman Adaptive Moving Average (KAMA) Trend-Following Strategy:
    - Dynamically adapts smoothing speed based on market efficiency vs noise.
    - Uses EfficiencyRatio, ADX, and Volatility filters to eliminate whipsaws.
    - Computes real-time statistical risk (VaR, CVaR) and mathematical expectations for open positions.
    """

    def __init__(self, config: KaufmanAdaptiveTrendConfig):
        super().__init__(config=config)
        self.closes: List[float] = []
        self.highs: List[float] = []
        self.lows: List[float] = []
        self.kama: Optional[float] = None
        self.last_kama: Optional[float] = None
        self.position_open = False
        self.entry_price: float = 0.0
        self.latest_forecast: Optional[PositionRiskMetrics] = None

        self.filter_pipeline = FilterPipeline([
            EfficiencyRatioNoiseFilter(period=self.config.er_period, min_efficiency=self.config.min_efficiency),
            ADXTrendStrengthFilter(period=14, min_adx=self.config.min_adx),
            ATRVolatilityRegimeFilter(min_vol_pct=0.00001, max_vol_pct=0.08),
        ])
        self.forecaster = PositionRiskForecaster(lookback_periods=30, stop_atr_mult=2.0, target_atr_mult=3.5)

    def on_start(self):
        super().on_start()

    def on_bar(self, bar: Bar):
        if not self.is_matching_bar(bar):
            return

        self._append_bar(bar)
        if len(self.closes) < self.config.er_period + 2:
            return

        atr = self._calculate_atr()
        self._update_kama(float(bar.close))

        if self.kama is None or self.last_kama is None:
            return

        if self.position_open:
            self._manage_position(bar, atr)
        else:
            self._check_entry(bar, atr)

    def _append_bar(self, bar: Bar):
        self.closes.append(float(bar.close))
        self.highs.append(float(bar.high))
        self.lows.append(float(bar.low))
        if len(self.closes) > 100:
            self.closes.pop(0)
            self.highs.pop(0)
            self.lows.pop(0)

    def _calculate_atr(self) -> float:
        tr_list = [
            max(self.highs[i] - self.lows[i], abs(self.highs[i] - self.closes[i - 1]), abs(self.lows[i] - self.closes[i - 1]))
            for i in range(1, len(self.closes))
        ]
        return sum(tr_list[-14:]) / 14 if len(tr_list) >= 14 else 1.0

    def _update_kama(self, close: float):
        if len(self.closes) <= self.config.er_period:
            self.kama = close
            return

        self.last_kama = self.kama
        sample = self.closes[-self.config.er_period - 1:]
        change = abs(sample[-1] - sample[0])
        volatility = sum(abs(sample[i] - sample[i - 1]) for i in range(1, len(sample)))
        er = (change / volatility) if volatility > 0 else 0.0

        fast_sc = 2.0 / (self.config.fast_period + 1)
        slow_sc = 2.0 / (self.config.slow_period + 1)
        sc = (er * (fast_sc - slow_sc) + slow_sc) ** 2

        self.kama = self.last_kama + sc * (close - self.last_kama)

    def _check_entry(self, bar: Bar, atr: float):
        close = float(bar.close)
        is_bullish_slope = self.kama > self.last_kama
        is_price_above = close > self.kama

        if is_bullish_slope and is_price_above:
            passed, results = self.filter_pipeline.evaluate(self.closes, self.highs, self.lows, OrderSide.BUY, atr)
            if not passed:
                return

            self._open_long(close, atr)

    def _open_long(self, close: float, atr: float):
        self.log.info(f"[{self.instrument_id}] KAMA Trend Bullish Acceleration. Going long at {close:.2f}")
        qty = self.make_qty(self.config.trade_size)
        order = self.order_factory.market(self.instrument_id, OrderSide.BUY, qty, TimeInForce.GTC)
        self.submit_order(order)
        self.position_open = True
        self.entry_price = close
        self._update_forecast(close, atr)

    def _manage_position(self, bar: Bar, atr: float):
        close = float(bar.close)
        self._update_forecast(close, atr)

        # Exit when price crosses below adaptive KAMA or KAMA slope turns negative
        if close < self.kama or self.kama < self.last_kama:
            self.log.info(f"[{self.instrument_id}] KAMA Trend Exit ({close:.2f} < KAMA {self.kama:.2f}). Closing long.")
            qty = self.make_qty(self.config.trade_size)
            order = self.order_factory.market(self.instrument_id, OrderSide.SELL, qty, TimeInForce.GTC)
            self.submit_order(order)
            self.position_open = False

    def _update_forecast(self, current_price: float, atr: float):
        self.latest_forecast = self.forecaster.calculate_forecast(
            instrument_id=str(self.instrument_id),
            side=OrderSide.BUY,
            quantity=self.config.trade_size,
            entry_price=self.entry_price,
            current_price=current_price,
            price_history=self.closes,
            atr=atr,
            signal_strength=1.15,
        )
        m = self.latest_forecast
        self.log.info(
            f"[{self.instrument_id}] KAMA Pos Risk: VaR95=${m.var_95_amount:.2f} | CVaR95=${m.cvar_95_amount:.2f} | "
            f"EV=${m.expected_value_amount:.2f} ({m.expected_value_pct:.2%}) | WinProb={m.win_probability_forecast:.1%} | Sharpe={m.forecasted_sharpe_ratio:.2f}"
        )

    def on_stop(self):
        self.log.info(f"Stopping KaufmanAdaptiveTrendStrategy for {self.instrument_id}")
