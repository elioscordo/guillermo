"""
SuperTrend Dynamic Volatility Breakout Strategy
===============================================
Trend-following breakout system combining ATR volatility trailing channels with
multi-factor regime filtering and real-time statistical risk/expectation analytics.

Optimization & Tuning Tips:
---------------------------
1. `atr_multiplier`:
   - 2.0 to 2.5: Faster stop trailing for choppy or mean-reverting markets.
   - 3.0 to 3.5: Recommended for long macro trends (avoids premature stop-outs during pullbacks).
2. `atr_period`:
   - Standard is 10-14 bars. Higher values (20-30) produce smoother trailing levels.
3. `min_adx`:
   - Higher values (25-30) decrease trade frequency but significantly improve win-rate and profit factor.
4. `max_long_rsi`:
   - Set to 70-75 to prevent buying at local tops.
"""

from typing import List, Optional
from nautilus_trader.config import ImportableActorConfig
from nautilus_trader.model.data import Bar, BarType
from nautilus_trader.model.enums import OrderSide, TimeInForce
from nautilus_trader.trading.strategy import Strategy as NautilusStrategy

from argo.strategies.filters import (
    FilterPipeline,
    ADXTrendStrengthFilter,
    ATRVolatilityRegimeFilter,
    RSIExhaustionFilter,
)
from argo.strategies.forecaster import PositionRiskForecaster, PositionRiskMetrics


class SuperTrendBreakoutConfig(ImportableActorConfig):
    """
    Configuration parameters for SuperTrendBreakoutStrategy.

    Attributes:
        instrument_id: Nautilus InstrumentId string (e.g. 'EUR/USD.IB').
        bar_type: Bar aggregation string (e.g. 'EUR/USD.IB-1-MINUTE-MID-INTERNAL').
        atr_period: Lookback period for Average True Range calculation (default: 14).
        atr_multiplier: Volatility band distance multiplier for SuperTrend bands (default: 3.0).
        trade_size: Position order quantity in base units or contracts (default: 100.0).
        min_adx: Minimum ADX trend strength threshold required to permit entry (default: 22.0).
        max_long_rsi: Maximum RSI allowed for long entry to avoid exhaustion (default: 75.0).
        min_vol_pct: Minimum normalized ATR/price threshold to avoid dead liquidity (default: 0.001).
        max_vol_pct: Maximum normalized ATR/price threshold to avoid news spikes (default: 0.06).
    """
    instrument_id: str
    bar_type: str
    atr_period: int = 14
    atr_multiplier: float = 3.0
    trade_size: float = 100.0
    min_adx: float = 22.0
    max_long_rsi: float = 75.0
    min_vol_pct: float = 0.001
    max_vol_pct: float = 0.06


class SuperTrendBreakoutStrategy(NautilusStrategy):
    """
    SuperTrend Volatility Breakout Trend-Following Strategy:
    - Calculates dynamic SuperTrend bands based on ATR volatility multiples.
    - Applies a multi-factor FilterPipeline (ADX trend strength, volatility regime, RSI exhaustion).
    - Forecasts real-time position risk (VaR, CVaR) and mathematical expectations (EV, RRR, Sharpe).
    """

    def __init__(self, config: SuperTrendBreakoutConfig):
        super().__init__(config=config)
        self.config = config
        self.highs: List[float] = []
        self.lows: List[float] = []
        self.closes: List[float] = []
        self.position_open = False
        self.entry_price: float = 0.0
        self.current_trend: int = 0  # 1 for bull, -1 for bear
        self.supertrend_val: float = 0.0
        self.latest_forecast: Optional[PositionRiskMetrics] = None

        self._instrument_id = self.instrument_provider.get_instrument(self.config.instrument_id)
        self._bar_type = BarType.from_str(self.config.bar_type)

        self.filter_pipeline = FilterPipeline([
            ADXTrendStrengthFilter(period=self.config.atr_period, min_adx=self.config.min_adx),
            ATRVolatilityRegimeFilter(min_vol_pct=self.config.min_vol_pct, max_vol_pct=self.config.max_vol_pct),
            RSIExhaustionFilter(period=self.config.atr_period, max_long_rsi=self.config.max_long_rsi),
        ])
        self.forecaster = PositionRiskForecaster(lookback_periods=30, stop_atr_mult=2.0, target_atr_mult=4.0)

    def on_start(self):
        self.log.info(f"Starting SuperTrendBreakoutStrategy for {self._instrument_id}")
        self.subscribe_data(self._instrument_id, self._bar_type)

    def on_bar(self, bar: Bar):
        if bar.instrument_id != self._instrument_id.id:
            return

        self._append_bar_data(bar)
        if len(self.closes) < self.config.atr_period + 2:
            return

        atr = self._calculate_atr()
        prev_trend = self.current_trend
        self._update_supertrend(bar, atr)

        if self.position_open:
            self._manage_open_position(bar, atr)
        else:
            self._evaluate_entry(bar, prev_trend, atr)

    def _append_bar_data(self, bar: Bar):
        self.highs.append(float(bar.high))
        self.lows.append(float(bar.low))
        self.closes.append(float(bar.close))
        max_len = max(self.config.atr_period * 3, 60)
        if len(self.closes) > max_len:
            self.highs.pop(0)
            self.lows.pop(0)
            self.closes.pop(0)

    def _calculate_atr(self) -> float:
        tr_list = [
            max(self.highs[i] - self.lows[i], abs(self.highs[i] - self.closes[i - 1]), abs(self.lows[i] - self.closes[i - 1]))
            for i in range(1, len(self.closes))
        ]
        return sum(tr_list[-self.config.atr_period:]) / self.config.atr_period

    def _update_supertrend(self, bar: Bar, atr: float):
        hl2 = (float(bar.high) + float(bar.low)) / 2.0
        upper_band = hl2 + (self.config.atr_multiplier * atr)
        lower_band = hl2 - (self.config.atr_multiplier * atr)
        close = float(bar.close)

        if close > self.supertrend_val:
            self.current_trend = 1
            self.supertrend_val = lower_band
        else:
            self.current_trend = -1
            self.supertrend_val = upper_band

    def _evaluate_entry(self, bar: Bar, prev_trend: int, atr: float):
        close = float(bar.close)
        # Bullish SuperTrend flip
        if self.current_trend == 1 and prev_trend != 1:
            passed, results = self.filter_pipeline.evaluate(self.closes, self.highs, self.lows, OrderSide.BUY, atr)
            if not passed:
                reasons = "; ".join(r.reason for r in results if not r.passed)
                self.log.info(f"[{self._instrument_id}] SuperTrend entry rejected by filters: {reasons}")
                return

            self._execute_entry(close, atr)

    def _execute_entry(self, close: float, atr: float):
        order = self.order_factory.market(self._instrument_id, OrderSide.BUY, self.config.trade_size, TimeInForce.FOK)
        self.submit_order(order)
        self.position_open = True
        self.entry_price = close
        self._update_and_log_forecast(close, atr)

    def _manage_open_position(self, bar: Bar, atr: float):
        close = float(bar.close)
        self._update_and_log_forecast(close, atr)

        # Exit if trend reverses or price breaks below dynamic SuperTrend line
        if self.current_trend == -1 or close < self.supertrend_val:
            self.log.info(f"[{self._instrument_id}] SuperTrend Exit ({close:.2f} <= {self.supertrend_val:.2f}). Closing long.")
            order = self.order_factory.market(self._instrument_id, OrderSide.SELL, self.config.trade_size, TimeInForce.FOK)
            self.submit_order(order)
            self.position_open = False

    def _update_and_log_forecast(self, current_price: float, atr: float):
        self.latest_forecast = self.forecaster.calculate_forecast(
            instrument_id=str(self._instrument_id),
            side=OrderSide.BUY,
            quantity=self.config.trade_size,
            entry_price=self.entry_price,
            current_price=current_price,
            price_history=self.closes,
            atr=atr,
            signal_strength=1.2,
        )
        m = self.latest_forecast
        self.log.info(
            f"[{self._instrument_id}] Position Risk Forecast: VaR95=${m.var_95_amount:.2f} ({m.var_95_pct:.2%}), "
            f"CVaR95=${m.cvar_95_amount:.2f}, ExpVal=${m.expected_value_amount:.2f} ({m.expected_value_pct:.2%}), "
            f"WinProb={m.win_probability_forecast:.1%}, RRR={m.reward_to_risk_ratio:.2f}, SharpeForecast={m.forecasted_sharpe_ratio:.2f}"
        )

    def on_stop(self):
        self.log.info(f"Stopping SuperTrendBreakoutStrategy for {self._instrument_id}")
