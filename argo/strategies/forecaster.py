"""
Argo Position Risk & Expectation Forecaster
===========================================
Design Pattern: Strategy & Value Object Pattern

Calculates statistical forecasts for open positions:
1. Value at Risk (VaR 95%, VaR 99%) & Conditional VaR (Expected Shortfall).
2. Mathematical Expectation (EV), Win Probability, and Forecasted Reward-to-Risk Ratio (RRR).
3. Maximum Adverse Excursion (MAE), Maximum Favorable Excursion (MFE), and Forecasted Sharpe Ratio.

Optimization & Tuning Tips:
---------------------------
1. Lookback Window (`lookback_periods`):
   - Fast intraday bars (1m-5m): 30-50 bars gives responsive rolling volatility estimates.
   - Daily/Hourly bars: 20-30 bars captures current volatility regime without stale data.
2. Stop & Target Multipliers (`stop_atr_mult`, `target_atr_mult`):
   - For trend-following, target-to-stop ratio should ideally be >= 2.0 (e.g. stop_mult=2.0, target_mult=4.0).
   - In choppy markets, tighten target_mult to 2.5-3.0 to lock in profits before reversals.
3. Base Win Rate Prior (`base_win_rate`):
   - Calibrate base_win_rate from historical backtest distributions (typical trend systems range 40%-55%).
"""

from dataclasses import dataclass
import math
from typing import List, Dict, Any
from nautilus_trader.model.enums import OrderSide


@dataclass(frozen=True)
class PositionRiskMetrics:
    """
    Immutable Value Object encapsulating statistical risk forecasts and expectation metrics.

    Attributes:
        instrument_id: Identifier of the instrument.
        side: Direction of position ('LONG' or 'SHORT').
        quantity: Size/lot of the position.
        entry_price: Average fill price.
        current_price: Latest mark price.
        position_value: Total notional value (Quantity * Price).
        unrealized_pnl: Floating profit/loss in account currency.
        unrealized_pnl_pct: Floating return as decimal fraction.
        daily_volatility: Rolling standard deviation of returns.
        var_95_amount: 95% 1-period Value at Risk in currency (95% of losses will not exceed this).
        var_95_pct: 95% VaR expressed as percentage of position notional.
        var_99_amount: 99% Value at Risk (tail risk threshold).
        var_99_pct: 99% VaR expressed as percentage.
        cvar_95_amount: Conditional VaR (Expected Shortfall) - expected loss when VaR is breached.
        projected_stop_price: Dynamic ATR-based stop price level.
        projected_target_price: Dynamic ATR-based profit target level.
        risk_amount: Projected monetary loss if stop is hit.
        reward_amount: Projected monetary profit if target is hit.
        reward_to_risk_ratio: Ratio of projected reward to risk (Reward / Risk).
        win_probability_forecast: Probability of winning trade forecast based on signal & RRR.
        expected_value_amount: Mathematical expectation in currency per trade: (P_win * Reward) - (P_loss * Risk).
        expected_value_pct: Expected value as percentage of position notional.
        forecasted_sharpe_ratio: Annualized expected Sharpe ratio approximation.
        projected_mae_pct: Projected Maximum Adverse Excursion percentage.
        projected_mfe_pct: Projected Maximum Favorable Excursion percentage.
    """
    instrument_id: str
    side: str
    quantity: float
    entry_price: float
    current_price: float
    position_value: float
    unrealized_pnl: float
    unrealized_pnl_pct: float
    daily_volatility: float
    var_95_amount: float
    var_95_pct: float
    var_99_amount: float
    var_99_pct: float
    cvar_95_amount: float
    projected_stop_price: float
    projected_target_price: float
    risk_amount: float
    reward_amount: float
    reward_to_risk_ratio: float
    win_probability_forecast: float
    expected_value_amount: float
    expected_value_pct: float
    forecasted_sharpe_ratio: float
    projected_mae_pct: float
    projected_mfe_pct: float

    def to_dict(self) -> Dict[str, Any]:
        """Serializes metrics into a clean dictionary with standard rounding."""
        return {
            "instrument_id": self.instrument_id,
            "side": self.side,
            "quantity": self.quantity,
            "entry_price": round(self.entry_price, 4),
            "current_price": round(self.current_price, 4),
            "position_value": round(self.position_value, 2),
            "unrealized_pnl": round(self.unrealized_pnl, 2),
            "unrealized_pnl_pct": round(self.unrealized_pnl_pct, 4),
            "daily_volatility": round(self.daily_volatility, 4),
            "var_95_amount": round(self.var_95_amount, 2),
            "var_95_pct": round(self.var_95_pct, 4),
            "var_99_amount": round(self.var_99_amount, 2),
            "var_99_pct": round(self.var_99_pct, 4),
            "cvar_95_amount": round(self.cvar_95_amount, 2),
            "projected_stop_price": round(self.projected_stop_price, 4),
            "projected_target_price": round(self.projected_target_price, 4),
            "risk_amount": round(self.risk_amount, 2),
            "reward_amount": round(self.reward_amount, 2),
            "reward_to_risk_ratio": round(self.reward_to_risk_ratio, 2),
            "win_probability_forecast": round(self.win_probability_forecast, 3),
            "expected_value_amount": round(self.expected_value_amount, 2),
            "expected_value_pct": round(self.expected_value_pct, 4),
            "forecasted_sharpe_ratio": round(self.forecasted_sharpe_ratio, 2),
            "projected_mae_pct": round(self.projected_mae_pct, 4),
            "projected_mfe_pct": round(self.projected_mfe_pct, 4),
        }


class PositionRiskForecaster:
    """
    Statistical risk and expectation forecasting engine for active trading positions.
    """

    def __init__(
        self,
        lookback_periods: int = 30,
        stop_atr_mult: float = 2.0,
        target_atr_mult: float = 4.0,
        base_win_rate: float = 0.52,
    ):
        self.lookback = lookback_periods
        self.stop_mult = stop_atr_mult
        self.target_mult = target_atr_mult
        self.base_win_rate = base_win_rate

    def calculate_forecast(
        self,
        instrument_id: str,
        side: OrderSide,
        quantity: float,
        entry_price: float,
        current_price: float,
        price_history: List[float],
        atr: float,
        signal_strength: float = 1.0,
    ) -> PositionRiskMetrics:
        """
        Calculates comprehensive statistical risk and expectation forecast for a position.
        
        Args:
            instrument_id: String ID of the traded instrument.
            side: OrderSide (BUY for long, SELL for short).
            quantity: Position size units.
            entry_price: Average entry execution price.
            current_price: Current market price.
            price_history: Recent close price history for return volatility estimation.
            atr: Current Average True Range.
            signal_strength: Multiplier (>1.0 indicates strong high-conviction signal).
        """
        is_long = side == OrderSide.BUY
        pos_val = quantity * current_price
        unrealized_pnl = (current_price - entry_price) * quantity if is_long else (entry_price - current_price) * quantity
        unrealized_pnl_pct = (current_price - entry_price) / entry_price if is_long else (entry_price - current_price) / entry_price

        mean_ret, vol = self._calculate_volatility(price_history)
        var_95, cvar_95 = self._forecast_var_cvar(pos_val, vol, z_score=1.645)
        var_99, _ = self._forecast_var_cvar(pos_val, vol, z_score=2.326)

        stop_px, target_px = self._calculate_projected_levels(entry_price, is_long, atr)
        risk_amt = abs(entry_price - stop_px) * quantity
        reward_amt = abs(target_px - entry_price) * quantity
        rrr = reward_amt / max(risk_amt, 1e-6)

        win_prob = self._forecast_win_rate(signal_strength, rrr)
        ev_amt = (win_prob * reward_amt) - ((1.0 - win_prob) * risk_amt)
        ev_pct = ev_amt / max(pos_val, 1e-6)

        sharpe = self._forecast_sharpe(mean_ret, vol)
        mae_pct = (self.stop_mult * atr) / max(entry_price, 1e-6)
        mfe_pct = (self.target_mult * atr) / max(entry_price, 1e-6)

        return PositionRiskMetrics(
            instrument_id=instrument_id,
            side="LONG" if is_long else "SHORT",
            quantity=quantity,
            entry_price=entry_price,
            current_price=current_price,
            position_value=pos_val,
            unrealized_pnl=unrealized_pnl,
            unrealized_pnl_pct=unrealized_pnl_pct,
            daily_volatility=vol,
            var_95_amount=var_95,
            var_95_pct=var_95 / max(pos_val, 1e-6),
            var_99_amount=var_99,
            var_99_pct=var_99 / max(pos_val, 1e-6),
            cvar_95_amount=cvar_95,
            projected_stop_price=stop_px,
            projected_target_price=target_px,
            risk_amount=risk_amt,
            reward_amount=reward_amt,
            reward_to_risk_ratio=rrr,
            win_probability_forecast=win_prob,
            expected_value_amount=ev_amt,
            expected_value_pct=ev_pct,
            forecasted_sharpe_ratio=sharpe,
            projected_mae_pct=mae_pct,
            projected_mfe_pct=mfe_pct,
        )

    def _calculate_volatility(self, prices: List[float]) -> tuple[float, float]:
        """Calculates mean return and standard deviation over price history."""
        if len(prices) < 2:
            return 0.0, 0.01
        sample = prices[-self.lookback:]
        returns = [(sample[i] - sample[i - 1]) / sample[i - 1] for i in range(1, len(sample))]
        mean_ret = sum(returns) / len(returns)
        variance = sum((r - mean_ret) ** 2 for r in returns) / max(len(returns) - 1, 1)
        return mean_ret, math.sqrt(variance)

    def _forecast_var_cvar(self, position_value: float, volatility: float, z_score: float) -> tuple[float, float]:
        """Computes parametric VaR and Expected Shortfall (CVaR)."""
        var_amount = position_value * z_score * volatility
        pdf_z = (1.0 / math.sqrt(2 * math.pi)) * math.exp(-0.5 * (z_score ** 2))
        alpha = 0.05 if z_score < 2.0 else 0.01
        cvar_amount = position_value * volatility * (pdf_z / alpha)
        return var_amount, cvar_amount

    def _calculate_projected_levels(self, entry_price: float, is_long: bool, atr: float) -> tuple[float, float]:
        """Projects dynamic ATR stop and target price levels."""
        effective_atr = max(atr, entry_price * 0.005)
        if is_long:
            stop_price = entry_price - (self.stop_mult * effective_atr)
            target_price = entry_price + (self.target_mult * effective_atr)
        else:
            stop_price = entry_price + (self.stop_mult * effective_atr)
            target_price = entry_price - (self.target_mult * effective_atr)
        return max(stop_price, 0.01), max(target_price, 0.01)

    def _forecast_win_rate(self, signal_strength: float, rrr: float) -> float:
        """Estimates forecasted win probability adjusted for signal strength and RRR."""
        bounded_strength = max(0.5, min(signal_strength, 2.0))
        raw_prob = self.base_win_rate * bounded_strength * (2.0 / (1.0 + rrr)) ** 0.3
        return max(0.20, min(raw_prob, 0.85))

    def _forecast_sharpe(self, mean_ret: float, vol: float) -> float:
        """Annualized expected Sharpe ratio approximation."""
        if vol <= 1e-6:
            return 0.0
        annualized_return = mean_ret * 252
        annualized_vol = vol * math.sqrt(252)
        return (annualized_return - 0.02) / annualized_vol
