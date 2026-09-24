from nautilus_trader.trading.config import StrategyConfig
from nautilus_trader.model.data import Bar
from nautilus_trader.model.enums import OrderSide, TimeInForce

from argo.strategies.base import ArgoBaseStrategy


class RSIStrategyConfig(StrategyConfig, frozen=True):
    """
    Configuration for RSI Mean Reversion / Momentum Strategy.
    """
    instrument_id: str
    bar_type: str
    period: int = 14
    oversold: float = 30.0
    overbought: float = 70.0
    trade_size: float = 100.0


class RSIStrategy(ArgoBaseStrategy):
    """
    Relative Strength Index (RSI) strategy:
    - Buys when RSI drops below oversold threshold.
    - Closes / sells when RSI rises above overbought threshold.
    """

    def __init__(self, config: RSIStrategyConfig):
        super().__init__(config=config)
        self.prices: list[float] = []
        self.position_open = False

    def on_start(self):
        super().on_start()

    def on_bar(self, bar: Bar):
        if not self.is_matching_bar(bar):
            return

        close = float(bar.close)
        self.prices.append(close)
        if len(self.prices) > self.config.period + 1:
            self.prices.pop(0)

        if len(self.prices) <= self.config.period:
            return

        gains, losses = [], []
        for i in range(1, len(self.prices)):
            diff = self.prices[i] - self.prices[i - 1]
            if diff >= 0:
                gains.append(diff)
                losses.append(0.0)
            else:
                gains.append(0.0)
                losses.append(abs(diff))

        avg_gain = sum(gains) / len(gains)
        avg_loss = sum(losses) / len(losses)

        if avg_loss == 0:
            rsi = 100.0
        else:
            rs = avg_gain / avg_loss
            rsi = 100.0 - (100.0 / (1.0 + rs))

        if rsi <= self.config.oversold and not self.position_open:
            self.log.info(f"[{self.instrument_id}] RSI {rsi:.2f} <= {self.config.oversold}. Going long.")
            qty = self.make_qty(self.config.trade_size)
            order = self.order_factory.market(self.instrument_id, OrderSide.BUY, qty, TimeInForce.FOK)
            self.submit_order(order)
            self.position_open = True
        elif rsi >= self.config.overbought and self.position_open:
            self.log.info(f"[{self.instrument_id}] RSI {rsi:.2f} >= {self.config.overbought}. Closing long.")
            qty = self.make_qty(self.config.trade_size)
            order = self.order_factory.market(self.instrument_id, OrderSide.SELL, qty, TimeInForce.FOK)
            self.submit_order(order)
            self.position_open = False

    def on_stop(self):
        self.log.info(f"Stopping RSIStrategy for {self.instrument_id}")
