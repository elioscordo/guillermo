"""
Triple EMA Pullback & Continuation Trend Strategy
=================================================
Multi-horizon structural trend system (Fast/Medium/Slow EMAs) that identifies established
trend regimes and triggers entries on shallow pullbacks into the value zone.

Optimization & Tuning Tips:
---------------------------
1. Moving Average Alignment (`fast_period`, `medium_period`, `slow_period`):
   - Intraday (1m-15m): 9, 21, 55 for quick pullback identification.
   - Swing (1h-1d): 10, 30, 100 or 20, 50, 200 for major institutional macro trends.
2. ADX Filter (`min_adx`):
   - 25.0 ensures the strategy only triggers during strong structural trends.
3. Pullback Depth (`max_rsi_entry`):
   - Set to 65-70 to ensure price has cooled off from overbought levels before continuation.
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
    RSIExhaustionFilter,
)
from argo.strategies.forecaster import PositionRiskForecaster, PositionRiskMetrics


class TripleMATrendConfig(StrategyConfig, frozen=True):
    """
    Configuration parameters for TripleMAContinuationStrategy.

    Attributes:
        instrument_id: Nautilus InstrumentId string (e.g. 'EUR/USD.IB').
        bar_type: Bar aggregation string (e.g. 'EUR/USD.IB-1-MINUTE-MID-EXTERNAL').
        fast_period: Fast EMA period for short-term momentum (default: 10).
        medium_period: Medium EMA period defining value zone dynamic support (default: 25).
        slow_period: Slow EMA period defining structural trend regime (default: 50).
        trade_size: Position order quantity in base units or contracts (default: 100.0).
        min_adx: Minimum ADX trend strength threshold (default: 20.0).
        max_rsi_entry: Maximum RSI allowed on continuation entry (default: 68.0).
    """
    instrument_id: str
    bar_type: str
    fast_period: int = 10
    medium_period: int = 25
    slow_period: int = 50
    trade_size: float = 100.0
    min_adx: float = 20.0
    max_rsi_entry: float = 68.0


class TripleMAContinuationStrategy(ArgoBaseStrategy):
    """
    Triple EMA Trend Continuation Strategy:
    - Verifies multi-timeframe structural regime alignment: Fast EMA > Medium EMA > Slow EMA.
    - Triggers high-probability entries on shallow pullbacks into the value zone (Medium EMA) with momentum re-ignition.
    - Employs multi-factor filters (ADX, ATR, RSI) and real-time statistical risk/expectation forecasting.
    """

    def __init__(self, config: TripleMATrendConfig):
        super().__init__(config=config)
        self.closes: List[float] = []
        self.highs: List[float] = []
        self.lows: List[float] = []
        self.fast_ema: Optional[float] = None
        self.medium_ema: Optional[float] = None
        self.slow_ema: Optional[float] = None
        self.position_open = False
        self.entry_price: float = 0.0
        self.latest_forecast: Optional[PositionRiskMetrics] = None

        self.filter_pipeline = FilterPipeline([
            ADXTrendStrengthFilter(period=14, min_adx=self.config.min_adx),
            ATRVolatilityRegimeFilter(min_vol_pct=0.001, max_vol_pct=0.06),
            RSIExhaustionFilter(period=14, max_long_rsi=self.config.max_rsi_entry),
        ])
        self.forecaster = PositionRiskForecaster(lookback_periods=30, stop_atr_mult=2.5, target_atr_mult=5.0)

    def on_start(self):
        super().on_start()

    def on_bar(self, bar: Bar):
        if not self.is_matching_bar(bar):
            return

        self._append_bar(bar)
        self._update_emas(float(bar.close))

        if not self._is_warmed_up():
            return

        atr = self._calculate_atr()
        if self.position_open:
            self._manage_position(bar, atr)
        else:
            self._check_entry_trigger(bar, atr)

    def _append_bar(self, bar: Bar):
        self.closes.append(float(bar.close))
        self.highs.append(float(bar.high))
        self.lows.append(float(bar.low))
        if len(self.closes) > self.config.slow_period * 2:
            self.closes.pop(0)
            self.highs.pop(0)
            self.lows.pop(0)

    def _update_emas(self, close: float):
        k_f = 2.0 / (self.config.fast_period + 1)
        k_m = 2.0 / (self.config.medium_period + 1)
        k_s = 2.0 / (self.config.slow_period + 1)

        self.fast_ema = close if self.fast_ema is None else (close * k_f) + (self.fast_ema * (1 - k_f))
        self.medium_ema = close if self.medium_ema is None else (close * k_m) + (self.medium_ema * (1 - k_m))
        self.slow_ema = close if self.slow_ema is None else (close * k_s) + (self.slow_ema * (1 - k_s))

    def _is_warmed_up(self) -> bool:
        return len(self.closes) >= self.config.slow_period and self.slow_ema is not None

    def _calculate_atr(self) -> float:
        tr_list = [
            max(self.highs[i] - self.lows[i], abs(self.highs[i] - self.closes[i - 1]), abs(self.lows[i] - self.closes[i - 1]))
            for i in range(1, len(self.closes))
        ]
        return sum(tr_list[-14:]) / 14 if len(tr_list) >= 14 else 1.0

    def _check_entry_trigger(self, bar: Bar, atr: float):
        close = float(bar.close)
        is_bull_regime = self.fast_ema > self.medium_ema > self.slow_ema
        is_above_medium = close >= self.medium_ema

        if is_bull_regime and is_above_medium:
            passed, results = self.filter_pipeline.evaluate(self.closes, self.highs, self.lows, OrderSide.BUY, atr)
            if not passed:
                return

            self._open_long(close, atr)

    def _open_long(self, close: float, atr: float):
        self.log.info(f"[{self.instrument_id}] Triple MA Trend Alignment. Going long at {close:.2f}")
        qty = self.make_qty(self.config.trade_size)
        order = self.order_factory.market(self.instrument_id, OrderSide.BUY, qty, TimeInForce.GTC)
        self.submit_order(order)
        self.position_open = True
        self.entry_price = close
        self._update_forecast(close, atr)

    def _manage_position(self, bar: Bar, atr: float):
        close = float(bar.close)
        self._update_forecast(close, atr)

        # Exit if trend structure breaks (Fast EMA crosses below Medium EMA or price breaks below Medium EMA)
        if self.fast_ema < self.medium_ema or close < self.medium_ema - (0.5 * atr):
            self.log.info(f"[{self.instrument_id}] Triple MA Trend Breakdown ({close:.2f}). Closing long.")
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
            signal_strength=1.3,
        )
        m = self.latest_forecast
        self.log.info(
            f"[{self.instrument_id}] TripleMA Forecast: VaR95=${m.var_95_amount:.2f} | CVaR95=${m.cvar_95_amount:.2f} | "
            f"EV=${m.expected_value_amount:.2f} ({m.expected_value_pct:.2%}) | WinProb={m.win_probability_forecast:.1%} | RRR={m.reward_to_risk_ratio:.2f}"
        )

    def on_stop(self):
        self.log.info(f"Stopping TripleMAContinuationStrategy for {self.instrument_id}")
