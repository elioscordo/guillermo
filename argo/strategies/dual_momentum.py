"""
Dual Momentum Trend-Following Strategy
=====================================
Combines Absolute Momentum (macro 200-period SMA regime gate) with short-term
momentum breakout execution, multi-factor filtering, and position risk forecasting.
Optimized for index ETFs (QQQ, SPY).
"""

from typing import List, Optional
from nautilus_trader.trading.config import StrategyConfig
from nautilus_trader.model.data import Bar
from nautilus_trader.model.enums import OrderSide, TimeInForce
from nautilus_trader.model.objects import Quantity

from argo.strategies.base import ArgoBaseStrategy
from argo.strategies.filters import (
    FilterPipeline,
    ADXTrendStrengthFilter,
    ATRVolatilityRegimeFilter,
    RSIExhaustionFilter,
)
from argo.strategies.forecaster import PositionRiskForecaster, PositionRiskMetrics


class DualMomentumStrategyConfig(StrategyConfig, frozen=True):
    """Configuration parameters for DualMomentumStrategy."""

    instrument_id: str
    bar_type: str
    trade_size: float = 100.0
    sma_trend_period: int = 200
    momentum_period: int = 20
    atr_period: int = 14
    atr_multiplier: float = 2.5
    min_adx: float = 18.0
    max_long_rsi: float = 75.0
    min_vol_pct: float = 0.00001
    max_vol_pct: float = 0.08


class DualMomentumStrategy(ArgoBaseStrategy):
    """
    Dual Momentum Trend Strategy for NautilusTrader / Argo:
    - Absolute Momentum Gate: Longs permitted only above the macro SMA (e.g. 200 bars).
    - Relative Momentum Trigger: Enters on 20-period price momentum high breakout.
    - Risk Management: Dynamic trailing stop based on ATR multiple, plus real-time risk forecasting.
    """

    def __init__(self, config: DualMomentumStrategyConfig):
        super().__init__(config=config)
        self.closes: List[float] = []
        self.highs: List[float] = []
        self.lows: List[float] = []
        self.position_open = False
        self.entry_price: float = 0.0
        self.entry_qty: Optional[Quantity] = None
        self.trailing_stop: float = 0.0
        self.latest_forecast: Optional[PositionRiskMetrics] = None

        self.filter_pipeline = FilterPipeline([
            ADXTrendStrengthFilter(period=self.config.atr_period, min_adx=self.config.min_adx),
            ATRVolatilityRegimeFilter(min_vol_pct=self.config.min_vol_pct, max_vol_pct=self.config.max_vol_pct),
            RSIExhaustionFilter(period=self.config.atr_period, max_long_rsi=self.config.max_long_rsi),
        ])
        self.forecaster = PositionRiskForecaster(lookback_periods=30, stop_atr_mult=2.0, target_atr_mult=4.0)

    def on_start(self):
        super().on_start()
        self.log.info(
            f"DualMomentum Strategy Started: SMA={self.config.sma_trend_period}, "
            f"Mom={self.config.momentum_period}, Size={self.config.trade_size}"
        )

    def on_bar(self, bar: Bar):
        if not self.is_matching_bar(bar):
            return

        self._append_bar(bar)
        if len(self.closes) < max(self.config.sma_trend_period, self.config.momentum_period) + 1:
            return

        atr = self._calculate_atr()
        if self.position_open:
            self._manage_position(bar, atr)
        else:
            self._check_entry(bar, atr)

    def _append_bar(self, bar: Bar):
        self.closes.append(float(bar.close))
        self.highs.append(float(bar.high))
        self.lows.append(float(bar.low))
        max_buffer = max(self.config.sma_trend_period * 2, 500)
        if len(self.closes) > max_buffer:
            self.closes.pop(0)
            self.highs.pop(0)
            self.lows.pop(0)

    def _calculate_sma(self, period: int) -> float:
        return sum(self.closes[-period:]) / period

    def _calculate_atr(self) -> float:
        tr_list = [
            max(self.highs[i] - self.lows[i], abs(self.highs[i] - self.closes[i - 1]), abs(self.lows[i] - self.closes[i - 1]))
            for i in range(1, len(self.closes))
        ]
        p = self.config.atr_period
        return sum(tr_list[-p:]) / p if len(tr_list) >= p else 1.0

    def _is_absolute_bullish(self, close: float) -> bool:
        sma = self._calculate_sma(self.config.sma_trend_period)
        return close > sma

    def _is_momentum_breakout(self, close: float) -> bool:
        mom_window = self.highs[-self.config.momentum_period - 1: -1]
        return bool(mom_window and close >= max(mom_window))

    def _check_entry(self, bar: Bar, atr: float):
        close = float(bar.close)
        if not (self._is_absolute_bullish(close) and self._is_momentum_breakout(close)):
            return

        passed, results = self.filter_pipeline.evaluate(self.closes, self.highs, self.lows, OrderSide.BUY, atr)
        if not passed:
            return

        self._execute_entry(close, atr)

    def _execute_entry(self, close: float, atr: float):
        self.log.info(f"[{self.instrument_id}] Dual Momentum Buy Triggered @ {close:.2f}")
        qty = self.make_qty(self.config.trade_size)
        order = self.order_factory.market(self.instrument_id, OrderSide.BUY, qty, TimeInForce.GTC)
        self.submit_order(order)
        self.position_open = True
        self.entry_price = close
        self.entry_qty = qty
        self.trailing_stop = close - (self.config.atr_multiplier * atr)
        self._update_forecast(close, atr)

    def _manage_position(self, bar: Bar, atr: float):
        close = float(bar.close)
        highest_recent = max(self.highs[-self.config.momentum_period:])
        new_stop = highest_recent - (self.config.atr_multiplier * atr)
        self.trailing_stop = max(self.trailing_stop, new_stop)

        sma = self._calculate_sma(self.config.sma_trend_period)
        if close < self.trailing_stop or close < sma:
            self.log.info(f"[{self.instrument_id}] Exit Triggered @ {close:.2f} (Stop={self.trailing_stop:.2f}, SMA={sma:.2f})")
            qty = self.entry_qty or self.make_qty(self.config.trade_size)
            order = self.order_factory.market(self.instrument_id, OrderSide.SELL, qty, TimeInForce.GTC)
            self.submit_order(order)
            self.position_open = False
            self.entry_qty = None
        else:
            self._update_forecast(close, atr)

    def _update_forecast(self, current_price: float, atr: float):
        self.latest_forecast = self.forecaster.calculate_forecast(
            instrument_id=str(self.instrument_id),
            side=OrderSide.BUY,
            quantity=self.config.trade_size,
            entry_price=self.entry_price,
            current_price=current_price,
            price_history=self.closes,
            atr=atr,
            signal_strength=1.25,
        )

    def on_stop(self):
        self.log.info(f"Stopping DualMomentumStrategy for {self.instrument_id}")
