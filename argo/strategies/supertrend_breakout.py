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
from nautilus_trader.trading.config import StrategyConfig
from nautilus_trader.model.data import Bar, BarType
from nautilus_trader.model.enums import OrderSide, TimeInForce
from nautilus_trader.model.objects import Quantity
from nautilus_trader.trading.strategy import Strategy as NautilusStrategy

from argo.strategies.base import ArgoBaseStrategy
from argo.strategies.filters import (
    FilterPipeline,
    ADXTrendStrengthFilter,
    ATRVolatilityRegimeFilter,
    RSIExhaustionFilter,
)
from argo.strategies.forecaster import PositionRiskForecaster, PositionRiskMetrics


class SuperTrendBreakoutStrategyConfig(StrategyConfig, frozen=True):
    """
    Configuration parameters for SuperTrendBreakoutStrategy.

    Attributes:
        instrument_id: Nautilus InstrumentId string (e.g. 'EUR/USD.IB').
        bar_type: Bar aggregation string (e.g. 'EUR/USD.IB-1-MINUTE-MID-EXTERNAL').
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
    trade_size: float = 1.0
    min_adx: float = 15.0
    max_long_rsi: float = 80.0
    min_vol_pct: float = 0.00001
    max_vol_pct: float = 0.08


class SuperTrendBreakoutStrategy(ArgoBaseStrategy):
    """
    SuperTrend Volatility Breakout Trend-Following Strategy:
    - Calculates dynamic SuperTrend bands based on ATR volatility multiples.
    - Applies a multi-factor FilterPipeline (ADX trend strength, volatility regime, RSI exhaustion).
    - Forecasts real-time position risk (VaR, CVaR) and mathematical expectations (EV, RRR, Sharpe).
    """

    def __init__(self, config: SuperTrendBreakoutStrategyConfig):
        super().__init__(config=config)
        self.highs: List[float] = []
        self.lows: List[float] = []
        self.closes: List[float] = []
        self.position_open = False
        self.entry_price: float = 0.0
        self.entry_qty: Optional[Quantity] = None
        self.current_trend: int = 0  # 1 for bull, -1 for bear
        self.trend_traded: bool = False
        self.supertrend_val: float = 0.0
        self._prev_upper: Optional[float] = None
        self._prev_lower: Optional[float] = None
        self.bar_count: int = 0
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
            f"Configured SuperTrendBreakout: ATR={self.config.atr_period}, Mult={self.config.atr_multiplier}, "
            f"ADX>={self.config.min_adx}, RSI<={self.config.max_long_rsi}, Size={self.config.trade_size}"
        )

    def on_bar(self, bar: Bar):
        if not self.is_matching_bar(bar):
            return

        self.bar_count += 1
        self._append_bar_data(bar)
        if len(self.closes) < self.config.atr_period + 2:
            return

        atr = self._calculate_atr()
        prev_trend = self.current_trend
        self._update_supertrend(bar, atr)

        if self.bar_count % 500 == 0 or self.current_trend != prev_trend:
            trend_str = "BULLISH" if self.current_trend == 1 else "BEARISH"
            self.log.info(
                f"[{self.instrument_id}] Bar #{self.bar_count:,} | close={float(bar.close):.2f} | "
                f"trend={trend_str} | ST_val={self.supertrend_val:.2f} | ATR={atr:.2f} | in_pos={self.position_open}"
            )

        if self.position_open:
            self._manage_open_position(bar, atr)
        else:
            self._evaluate_entry(bar, prev_trend, atr)

    def _append_bar_data(self, bar: Bar):
        self.highs.append(float(bar.high))
        self.lows.append(float(bar.low))
        self.closes.append(float(bar.close))
        max_len = max(self.config.atr_period * 4, 100)
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
        basic_upper = hl2 + (self.config.atr_multiplier * atr)
        basic_lower = hl2 - (self.config.atr_multiplier * atr)
        close = float(bar.close)

        if self._prev_upper is None or self._prev_lower is None:
            self._prev_upper = basic_upper
            self._prev_lower = basic_lower
            self.supertrend_val = basic_lower
            self.current_trend = 1
            return

        prev_close = self.closes[-2] if len(self.closes) >= 2 else close
        final_upper = basic_upper if basic_upper < self._prev_upper or prev_close > self._prev_upper else self._prev_upper
        final_lower = basic_lower if basic_lower > self._prev_lower or prev_close < self._prev_lower else self._prev_lower

        if self.current_trend == 1:
            if close < final_lower:
                self.current_trend = -1
                self.supertrend_val = final_upper
                self.trend_traded = False
            else:
                self.supertrend_val = final_lower
        else:
            if close > final_upper:
                self.current_trend = 1
                self.supertrend_val = final_lower
                self.trend_traded = False
            else:
                self.supertrend_val = final_upper

        self._prev_upper = final_upper
        self._prev_lower = final_lower

    def _evaluate_entry(self, bar: Bar, prev_trend: int, atr: float):
        close = float(bar.close)
        if self.current_trend == 1 and prev_trend != 1:
            self.trend_traded = False
            self.log.info(f"[{self.instrument_id}] SuperTrend BULLISH FLIP triggered at close={close:.2f} (ATR={atr:.2f})")

        # Evaluate entry when trend is bullish, not in position, and haven't entered yet in this wave
        if self.current_trend == 1 and not self.position_open and not self.trend_traded:
            passed, results = self.filter_pipeline.evaluate(self.closes, self.highs, self.lows, OrderSide.BUY, atr)
            if not passed:
                return

            scores_str = ", ".join(f"{r.filter_name}={r.score:.2f}" for r in results)
            self.log.info(f"[{self.instrument_id}] ALL FILTERS PASSED [{scores_str}] -> Executing LONG entry at {close:.2f}")
            self._execute_entry(close, atr)
            self.trend_traded = True

    def _get_safe_qty(self, close: float) -> Quantity:
        size = self.config.trade_size
        notional = size * close
        if notional > 50_000.0 and close > 100.0:
            safe_size = max(0.01, round(10_000.0 / close, 4))
            self.log.info(
                f"[{self.instrument_id}] Notional protection: {size} units @ {close:.2f} = ${notional:,.2f} "
                f"exceeds capital. Sizing down to {safe_size} units ($10k notional)."
            )
            size = safe_size
        return self.make_qty(size)

    def _execute_entry(self, close: float, atr: float):
        qty = self._get_safe_qty(close)
        order = self.order_factory.market(self.instrument_id, OrderSide.BUY, qty, TimeInForce.GTC)
        self.submit_order(order)
        self.position_open = True
        self.entry_price = close
        self.entry_qty = qty
        self._update_and_log_forecast(close, atr)

    def _manage_open_position(self, bar: Bar, atr: float):
        close = float(bar.close)
        if self.bar_count % 500 == 0:
            self._update_and_log_forecast(close, atr)

        # Exit if trend reverses or price breaks below dynamic SuperTrend line
        if self.current_trend == -1 or close < self.supertrend_val:
            self.log.info(
                f"[{self.instrument_id}] SuperTrend Exit triggered ({close:.2f} <= {self.supertrend_val:.2f}). "
                f"Closing long position."
            )
            qty = self.entry_qty or self._get_safe_qty(close)
            order = self.order_factory.market(self.instrument_id, OrderSide.SELL, qty, TimeInForce.GTC)
            self.submit_order(order)
            self.position_open = False
            self.entry_qty = None

    def _update_and_log_forecast(self, current_price: float, atr: float):
        self.latest_forecast = self.forecaster.calculate_forecast(
            instrument_id=str(self.instrument_id),
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
            f"[{self.instrument_id}] Position Risk Forecast: VaR95=${m.var_95_amount:.2f} ({m.var_95_pct:.2%}), "
            f"CVaR95=${m.cvar_95_amount:.2f}, ExpVal=${m.expected_value_amount:.2f} ({m.expected_value_pct:.2%}), "
            f"WinProb={m.win_probability_forecast:.1%}, RRR={m.reward_to_risk_ratio:.2f}, SharpeForecast={m.forecasted_sharpe_ratio:.2f}"
        )

    def on_stop(self):
        self.log.info(f"Stopping SuperTrendBreakoutStrategy for {self.instrument_id}")
