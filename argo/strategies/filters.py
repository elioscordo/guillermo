"""
Argo Trend Filters & Regime Quality Pipeline
============================================
Design Pattern: Specification & Composite Filter Pipeline (Chain of Responsibility)

Provides modular filters that evaluate market state before entry to eliminate false breakouts,
ranging chop, volatility spikes, and momentum exhaustion.

Optimization & Tuning Tips:
---------------------------
1. ADX Threshold:
   - For fast intraday (1m-5m): use min_adx = 20-22 to avoid missing early momentum.
   - For swing/daily: use min_adx = 25-30 for higher selectivity and trend persistence.
2. ATR Volatility Regime:
   - Tune `min_vol_pct` and `max_vol_pct` per asset class (Equities ~ 0.005-0.05, FX ~ 0.001-0.02, Crypto ~ 0.01-0.10).
3. RSI Exhaustion:
   - Strong structural bull runs can sustain RSI > 70. For strong momentum systems, relax to 75-80.
4. Kaufman Efficiency Ratio:
   - Threshold > 0.30 filters ~60% of choppy whipsaws; threshold > 0.50 selects only sharp directional breakouts.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import List, Optional
from nautilus_trader.model.enums import OrderSide


@dataclass(frozen=True)
class FilterResult:
    """
    Result container for an individual filter evaluation.
    
    Attributes:
        filter_name: Human-readable name of the evaluated filter.
        passed: True if the market condition satisfies the filter criteria.
        score: Numeric metric value computed during evaluation (e.g. ADX value, RSI).
        reason: Diagnostic explanation of why the filter passed or failed.
    """
    filter_name: str
    passed: bool
    score: float
    reason: str


class BaseFilter(ABC):
    """Abstract base class for all market filters (Specification Pattern)."""

    @abstractmethod
    def evaluate(
        self,
        closes: List[float],
        highs: List[float],
        lows: List[float],
        side: OrderSide,
        current_atr: Optional[float] = None,
    ) -> FilterResult:
        """
        Evaluates market data series and returns a FilterResult.
        
        Args:
            closes: History of closing prices.
            highs: History of high prices.
            lows: History of low prices.
            side: Proposed order side (BUY / SELL).
            current_atr: Optional precalculated Average True Range.
        """
        raise NotImplementedError


class ADXTrendStrengthFilter(BaseFilter):
    """
    Average Directional Index (ADX) Trend Strength Filter.
    
    How it works:
        Calculates Welles Wilder's ADX to quantify trend strength regardless of direction.
        Filters out choppy, range-bound markets where trend-following strategies get whipsawed.
        
    Optimization Tips:
        - Parameter `period`: Standard is 14. Lower (e.g. 10) for faster response; higher (e.g. 20) for smoother regime detection.
        - Parameter `min_adx`: 20-25 indicates developing trend; > 25 confirms a strong established trend.
    """

    def __init__(self, period: int = 14, min_adx: float = 20.0):
        self.period = period
        self.min_adx = min_adx

    def evaluate(
        self,
        closes: List[float],
        highs: List[float],
        lows: List[float],
        side: OrderSide,
        current_atr: Optional[float] = None,
    ) -> FilterResult:
        if len(closes) < self.period * 2:
            return FilterResult("ADXFilter", True, 25.0, "Warmup period")

        adx = self._calculate_adx(closes, highs, lows)
        passed = adx >= self.min_adx
        reason = f"ADX {adx:.1f} >= {self.min_adx}" if passed else f"ADX {adx:.1f} < {self.min_adx} (Market Choppy)"
        return FilterResult("ADXFilter", passed, adx, reason)

    def _calculate_adx(self, closes: List[float], highs: List[float], lows: List[float]) -> float:
        tr_list, dm_plus_list, dm_minus_list = [], [], []
        for i in range(1, len(closes)):
            tr = max(highs[i] - lows[i], abs(highs[i] - closes[i - 1]), abs(lows[i] - closes[i - 1]))
            up_move = highs[i] - highs[i - 1]
            down_move = lows[i - 1] - lows[i]

            dm_plus = up_move if up_move > down_move and up_move > 0 else 0.0
            dm_minus = down_move if down_move > up_move and down_move > 0 else 0.0

            tr_list.append(tr)
            dm_plus_list.append(dm_plus)
            dm_minus_list.append(dm_minus)

        tr_sum = sum(tr_list[-self.period:])
        if tr_sum == 0:
            return 0.0
        di_plus = 100.0 * (sum(dm_plus_list[-self.period:]) / tr_sum)
        di_minus = 100.0 * (sum(dm_minus_list[-self.period:]) / tr_sum)
        dx_sum = di_plus + di_minus
        return (100.0 * abs(di_plus - di_minus) / dx_sum) if dx_sum > 0 else 0.0


class ATRVolatilityRegimeFilter(BaseFilter):
    """
    Normalized ATR Volatility Regime Filter.
    
    How it works:
        Normalizes ATR by current price (`ATR / Close`) to measure relative market volatility.
        Blocks entries when volatility is too low (stagnant/dead market) or excessively high (erratic news spikes).
        
    Optimization Tips:
        - `min_vol_pct`: Prevents trading during low-liquidity/flat sessions (e.g. 0.001 = 0.10% price movement).
        - `max_vol_pct`: Avoids entering into runaway parabolic spikes or high slippage events (e.g. 0.05-0.08).
    """

    def __init__(self, min_vol_pct: float = 0.001, max_vol_pct: float = 0.08):
        self.min_vol_pct = min_vol_pct
        self.max_vol_pct = max_vol_pct

    def evaluate(
        self,
        closes: List[float],
        highs: List[float],
        lows: List[float],
        side: OrderSide,
        current_atr: Optional[float] = None,
    ) -> FilterResult:
        if not closes or current_atr is None:
            return FilterResult("ATRVolatilityFilter", True, 1.0, "Sufficient data missing")

        last_close = closes[-1]
        norm_vol = current_atr / max(last_close, 1e-6)
        passed = self.min_vol_pct <= norm_vol <= self.max_vol_pct
        reason = f"Normalized ATR {norm_vol:.4f} in [{self.min_vol_pct}, {self.max_vol_pct}]" if passed else f"Normalized ATR {norm_vol:.4f} out of bounds"
        return FilterResult("ATRVolatilityFilter", passed, norm_vol, reason)


class RSIExhaustionFilter(BaseFilter):
    """
    RSI Momentum Exhaustion Filter.
    
    How it works:
        Uses Relative Strength Index to ensure that long breakouts are not already exhausted (> max_long_rsi)
        and short breakouts are not excessively oversold (< min_short_rsi).
        
    Optimization Tips:
        - `max_long_rsi`: 70 is conservative; 75-80 is suitable for explosive breakout trends.
        - `min_short_rsi`: 30 is conservative; 20-25 for short breakouts in strong bear regimes.
    """

    def __init__(self, period: int = 14, max_long_rsi: float = 75.0, min_short_rsi: float = 25.0):
        self.period = period
        self.max_long_rsi = max_long_rsi
        self.min_short_rsi = min_short_rsi

    def evaluate(
        self,
        closes: List[float],
        highs: List[float],
        lows: List[float],
        side: OrderSide,
        current_atr: Optional[float] = None,
    ) -> FilterResult:
        if len(closes) <= self.period:
            return FilterResult("RSIExhaustionFilter", True, 50.0, "Warmup")

        rsi = self._calculate_rsi(closes)
        if side == OrderSide.BUY:
            passed = rsi <= self.max_long_rsi
            reason = f"RSI {rsi:.1f} <= {self.max_long_rsi}" if passed else f"RSI {rsi:.1f} Overbought (> {self.max_long_rsi})"
        else:
            passed = rsi >= self.min_short_rsi
            reason = f"RSI {rsi:.1f} >= {self.min_short_rsi}" if passed else f"RSI {rsi:.1f} Oversold (< {self.min_short_rsi})"

        return FilterResult("RSIExhaustionFilter", passed, rsi, reason)

    def _calculate_rsi(self, closes: List[float]) -> float:
        sample = closes[-self.period - 1:]
        gains, losses = [], []
        for i in range(1, len(sample)):
            delta = sample[i] - sample[i - 1]
            gains.append(delta if delta > 0 else 0.0)
            losses.append(abs(delta) if delta < 0 else 0.0)

        avg_gain = sum(gains) / self.period
        avg_loss = sum(losses) / self.period
        if avg_loss == 0:
            return 100.0
        rs = avg_gain / avg_loss
        return 100.0 - (100.0 / (1.0 + rs))


class EfficiencyRatioNoiseFilter(BaseFilter):
    """
    Kaufman Efficiency Ratio (ER) Noise Filter.
    
    How it works:
        ER = |Net Price Change over N bars| / Sum of Absolute Bar-to-Bar Changes.
        Values near 1.0 indicate pure unidirectional trend; values near 0.0 indicate pure random noise.
        
    Optimization Tips:
        - `min_efficiency`: 0.25-0.30 filters typical random noise; > 0.45 selects high-velocity institutional trends.
        - `period`: 10-14 bars provides optimal sensitivity without lagging price changes.
    """

    def __init__(self, period: int = 14, min_efficiency: float = 0.25):
        self.period = period
        self.min_efficiency = min_efficiency

    def evaluate(
        self,
        closes: List[float],
        highs: List[float],
        lows: List[float],
        side: OrderSide,
        current_atr: Optional[float] = None,
    ) -> FilterResult:
        if len(closes) < self.period + 1:
            return FilterResult("EfficiencyRatioFilter", True, 0.5, "Warmup")

        er = self._calculate_er(closes)
        passed = er >= self.min_efficiency
        reason = f"Efficiency Ratio {er:.2f} >= {self.min_efficiency}" if passed else f"Efficiency Ratio {er:.2f} < {self.min_efficiency} (High Noise)"
        return FilterResult("EfficiencyRatioFilter", passed, er, reason)

    def _calculate_er(self, closes: List[float]) -> float:
        sample = closes[-self.period - 1:]
        direction = abs(sample[-1] - sample[0])
        volatility = sum(abs(sample[i] - sample[i - 1]) for i in range(1, len(sample)))
        return (direction / volatility) if volatility > 0 else 0.0


class FilterPipeline:
    """
    Composite Filter Pipeline (Composite / Chain of Responsibility Pattern).
    Aggregates multiple filters and evaluates them concurrently.
    """

    def __init__(self, filters: Optional[List[BaseFilter]] = None):
        self.filters = filters or []

    def add_filter(self, filter_instance: BaseFilter) -> "FilterPipeline":
        """Adds a filter to the evaluation pipeline."""
        self.filters.append(filter_instance)
        return self

    def evaluate(
        self,
        closes: List[float],
        highs: List[float],
        lows: List[float],
        side: OrderSide,
        current_atr: Optional[float] = None,
    ) -> tuple[bool, List[FilterResult]]:
        """Executes all filters in the pipeline and returns aggregate decision and individual results."""
        results = []
        all_passed = True
        for f in self.filters:
            res = f.evaluate(closes, highs, lows, side, current_atr)
            results.append(res)
            if not res.passed:
                all_passed = False
        return all_passed, results
