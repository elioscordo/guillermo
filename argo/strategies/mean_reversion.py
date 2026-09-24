from nautilus_trader.trading.config import StrategyConfig
from nautilus_trader.model.data import Bar
from nautilus_trader.model.enums import OrderSide, TimeInForce

from argo.strategies.base import ArgoBaseStrategy


class BBMeanReversionConfig(StrategyConfig, frozen=True):
    """
    Configuration for Bollinger Bands Mean Reversion Strategy.
    """
    instrument_id: str
    bar_type: str
    period: int = 20
    num_std: float = 2.0
    trade_size: float = 100.0


class BBMeanReversionStrategy(ArgoBaseStrategy):
    """
    Bollinger Bands Mean Reversion: buys when price touches/drops below the lower band,
    and closes when price reverts to the upper band or moving average.
    """

    def __init__(self, config: BBMeanReversionConfig):
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
        if len(self.prices) > self.config.period:
            self.prices.pop(0)

        if len(self.prices) < self.config.period:
            return

        mean = sum(self.prices) / len(self.prices)
        variance = sum((p - mean) ** 2 for p in self.prices) / len(self.prices)
        std = variance ** 0.5

        lower_band = mean - (self.config.num_std * std)
        upper_band = mean + (self.config.num_std * std)

        if close <= lower_band and not self.position_open:
            self.log.info(f"[{self.instrument_id}] Price {close:.2f} <= Lower Band {lower_band:.2f}. Going long.")
            qty = self.make_qty(self.config.trade_size)
            order = self.order_factory.market(self.instrument_id, OrderSide.BUY, qty, TimeInForce.FOK)
            self.submit_order(order)
            self.position_open = True
        elif close >= upper_band and self.position_open:
            self.log.info(f"[{self.instrument_id}] Price {close:.2f} >= Upper Band {upper_band:.2f}. Closing long.")
            qty = self.make_qty(self.config.trade_size)
            order = self.order_factory.market(self.instrument_id, OrderSide.SELL, qty, TimeInForce.FOK)
            self.submit_order(order)
            self.position_open = False

    def on_stop(self):
        self.log.info(f"Stopping BBMeanReversionStrategy for {self.instrument_id}")