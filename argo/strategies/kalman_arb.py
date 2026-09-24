from decimal import Decimal
import numpy as np

from nautilus_trader.common.enums import LogColor
from nautilus_trader.config import StrategyConfig
from nautilus_trader.core.data import Bar, BarType
from nautilus_trader.model.enums import OrderSide, TimeInForce
from nautilus_trader.model.identifiers import InstrumentId
from nautilus_trader.model.orders import MarketOrder
from nautilus_trader.trading.strategy import Strategy


class LogKalmanStatArbConfig(StrategyConfig, frozen=True):
    constituent_id: str          # e.g. "NVDA.XNAS" (y)
    hedge_id: str                # e.g. "SMH.XNAS"  (x)
    constituent_bar_type: str
    hedge_bar_type: str
    target_dollar_allocation: Decimal = Decimal("50000")  # Fixed capital per leg ($50k)
    entry_z_score: float = 2.0
    exit_z_score: float = 0.4
    stop_z_score: float = 3.5
    kalman_delta: float = 1e-4
    kalman_r: float = 1e-3
    z_score_window: int = 30


class LogKalmanStatArbStrategy(Strategy):
    """
    Log-Space Cointegration Pairs Strategy with Dollar-Neutral Position Sizing.
    """

    def __init__(self, config: LogKalmanStatArbConfig) -> None:
        super().__init__(config)

        self.inst_y = InstrumentId.from_str(config.constituent_id)
        self.inst_x = InstrumentId.from_str(config.hedge_id)

        self.bar_type_y = BarType.from_str(config.constituent_bar_type)
        self.bar_type_x = BarType.from_str(config.hedge_bar_type)

        self.kf = LogKalmanHedgeEstimator(
            delta=config.kalman_delta,
            r_variance=config.kalman_r,
        )

        self.residuals: list[float] = []
        self.window = config.z_score_window

        self.last_px_y: float | None = None
        self.last_px_x: float | None = None
        self.current_regime: int = 0

    def on_start(self) -> None:
        self.subscribe_bars(self.bar_type_y)
        self.subscribe_bars(self.bar_type_x)
        self.log.info(f"Log-Space StatArb active: {self.inst_y} / {self.inst_x}")

    def on_bar(self, bar: Bar) -> None:
        if bar.bar_type == self.bar_type_y:
            self.last_px_y = float(bar.close)
        elif bar.bar_type == self.bar_type_x:
            self.last_px_x = float(bar.close)

        if self.last_px_y is not None and self.last_px_x is not None:
            self._evaluate_pairs_logic(self.last_px_y, self.last_px_x)

    def _evaluate_pairs_logic(self, py: float, px: float) -> None:
        # 1. Update filter in log space
        error, beta, alpha = self.kf.update(y_price=py, x_price=px)

        self.residuals.append(error)
        if len(self.residuals) > self.window:
            self.residuals.pop(0)

        if len(self.residuals) < self.window:
            return

        mean_err = np.mean(self.residuals)
        std_err = np.std(self.residuals)

        if std_err == 0.0 or np.isnan(std_err):
            return

        # Standardized deviation in percentage divergence
        z_score = (error - mean_err) / std_err

        # 2. Risk Stop Exit
        if abs(z_score) >= self.config.stop_z_score and self.current_regime != 0:
            self.log.warn(f"Stop triggered: Z={z_score:.2f} beyond threshold. Flattening.")
            self._flatten_pair()
            return

        # 3. Mean Reversion Exit
        if self.current_regime == 1 and z_score >= -self.config.exit_z_score:
            self.log.info(f"Take profit hit for Long Spread. Z={z_score:.2f}")
            self._flatten_pair()
            return

        if self.current_regime == -1 and z_score <= self.config.exit_z_score:
            self.log.info(f"Take profit hit for Short Spread. Z={z_score:.2f}")
            self._flatten_pair()
            return

        # 4. Entry Checks
        if self.current_regime == 0:
            if z_score <= -self.config.entry_z_score:
                self.log.info(
                    f"Entering Long Spread (Long {self.inst_y} / Short {self.inst_x}). Z: {z_score:.2f}, Elasticity Beta: {beta:.3f}",
                    color=LogColor.GREEN,
                )
                self._execute_dollar_neutral_pair(long_y=True, py=py, px=px, beta=beta)
                self.current_regime = 1

            elif z_score >= self.config.entry_z_score:
                self.log.info(
                    f"Entering Short Spread (Short {self.inst_y} / Long {self.inst_x}). Z: {z_score:.2f}, Elasticity Beta: {beta:.3f}",
                    color=LogColor.MAGENTA,
                )
                self._execute_dollar_neutral_pair(long_y=False, py=py, px=px, beta=beta)
                self.current_regime = -1

    def _execute_dollar_neutral_pair(
        self, long_y: bool, py: float, px: float, beta: float
    ) -> None:
        """
        Translates log-beta and nominal prices into discrete share orders.
        """
        target_usd = float(self.config.target_dollar_allocation)

        # Primary leg share count based on allocated capital
        shares_y = max(1, int(round(target_usd / py)))

        # Hedge leg shares: (Target Dollars * Beta) / Price_X
        # Equates to: shares_y * (py / px) * beta
        dollar_hedge_target = (shares_y * py) * abs(beta)
        shares_x = max(1, int(round(dollar_hedge_target / px)))

        side_y = OrderSide.BUY if long_y else OrderSide.SELL
        side_x = OrderSide.SELL if long_y else OrderSide.BUY

        order_y: MarketOrder = self.order_factory.market(
            instrument_id=self.inst_y,
            order_side=side_y,
            quantity=Decimal(str(shares_y)),
            time_in_force=TimeInForce.GTC,
        )
        order_x: MarketOrder = self.order_factory.market(
            instrument_id=self.inst_x,
            order_side=side_x,
            quantity=Decimal(str(shares_x)),
            time_in_force=TimeInForce.GTC,
        )

        self.submit_order(order_y)
        self.submit_order(order_x)
        self.log.info(
            f"Filled Dollar-Neutral Leg: {shares_y}x {self.inst_y} (${shares_y * py:,.0f}) "
            f"vs {shares_x}x {self.inst_x} (${shares_x * px:,.0f})"
        )

    def _flatten_pair(self) -> None:
        self.close_all_positions(self.inst_y)
        self.close_all_positions(self.inst_x)
        self.current_regime = 0

    def on_stop(self) -> None:
        self.cancel_all_orders(self.inst_y)
        self.cancel_all_orders(self.inst_x)
        self._flatten_pair()