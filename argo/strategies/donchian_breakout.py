from nautilus_trader.trading.config import StrategyConfig
from nautilus_trader.model.data import Bar
from nautilus_trader.model.enums import OrderSide, TimeInForce

from argo.strategies.base import ArgoBaseStrategy


class DonchianBreakoutConfig(StrategyConfig, frozen=True):
    """
    Configuration for Donchian Channel (Turtle Breakout) Strategy.
    """
    instrument_id: str
    bar_type: str
    entry_period: int = 20
    exit_period: int = 10
    trade_size: float = 100.0


class DonchianBreakoutStrategy(ArgoBaseStrategy):
    """
    Donchian Breakout Strategy (Classic Turtle Trading):
    - Goes long when price breaks above the highest high of the last N bars (entry_period).
    - Exits when price breaks below the lowest low of the last M bars (exit_period).
    """

    def __init__(self, config: DonchianBreakoutConfig):
        super().__init__(config=config)
        self.highs: list[float] = []
        self.lows: list[float] = []
        self.position_open = False

    def on_start(self):
        super().on_start()

    def on_bar(self, bar: Bar):
        if not self.is_matching_bar(bar):
            return

        high = float(bar.high)
        low = float(bar.low)
        close = float(bar.close)

        max_lookback = max(self.config.entry_period, self.config.exit_period)

        if len(self.highs) >= self.config.entry_period:
            highest_high = max(self.highs[-self.config.entry_period:])
            if close > highest_high and not self.position_open:
                self.log.info(f"[{self.instrument_id}] Donchian High Breakout ({close:.2f} > {highest_high:.2f}). Going long.")
                qty = self.make_qty(self.config.trade_size)
                order = self.order_factory.market(self.instrument_id, OrderSide.BUY, qty, TimeInForce.FOK)
                self.submit_order(order)
                self.position_open = True

        if len(self.lows) >= self.config.exit_period and self.position_open:
            lowest_low = min(self.lows[-self.config.exit_period:])
            if close < lowest_low:
                self.log.info(f"[{self.instrument_id}] Donchian Low Exit ({close:.2f} < {lowest_low:.2f}). Closing long.")
                qty = self.make_qty(self.config.trade_size)
                order = self.order_factory.market(self.instrument_id, OrderSide.SELL, qty, TimeInForce.FOK)
                self.submit_order(order)
                self.position_open = False

        self.highs.append(high)
        self.lows.append(low)
        if len(self.highs) > max_lookback:
            self.highs.pop(0)
            self.lows.pop(0)

    def on_stop(self):
        self.log.info(f"Stopping DonchianBreakoutStrategy for {self.instrument_id}")
