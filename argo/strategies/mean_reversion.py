from nautilus_trader.config import ImportableActorConfig
from nautilus_trader.model.data import Bar, BarType
from nautilus_trader.model.enums import OrderSide, TimeInForce
from nautilus_trader.trading.strategy import Strategy as NautilusStrategy


class BBMeanReversionConfig(ImportableActorConfig):
    """
    Configuration for Bollinger Bands Mean Reversion Strategy.
    """
    instrument_id: str
    bar_type: str
    period: int = 20
    num_std: float = 2.0
    trade_size: float = 100.0


class BBMeanReversionStrategy(NautilusStrategy):
    """
    Bollinger Bands Mean Reversion: buys when price touches/drops below the lower band,
    and closes when price reverts to the upper band or moving average.
    """

    def __init__(self, config: BBMeanReversionConfig):
        super().__init__(config=config)
        self.config = config
        self.prices: list[float] = []
        self.position_open = False
        self._instrument_id = self.instrument_provider.get_instrument(self.config.instrument_id)
        self._bar_type = BarType.from_str(self.config.bar_type)

    def on_start(self):
        self.log.info(f"Starting BBMeanReversionStrategy for {self._instrument_id}")
        self.subscribe_data(self._instrument_id, self._bar_type)

    def on_bar(self, bar: Bar):
        if bar.instrument_id != self._instrument_id.id:
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
            self.log.info(f"[{self._instrument_id}] Price {close:.2f} <= Lower Band {lower_band:.2f}. Going long.")
            order = self.order_factory.market(self._instrument_id, OrderSide.BUY, self.config.trade_size, TimeInForce.FOK)
            self.submit_order(order)
            self.position_open = True
        elif close >= upper_band and self.position_open:
            self.log.info(f"[{self._instrument_id}] Price {close:.2f} >= Upper Band {upper_band:.2f}. Closing long.")
            order = self.order_factory.market(self._instrument_id, OrderSide.SELL, self.config.trade_size, TimeInForce.FOK)
            self.submit_order(order)
            self.position_open = False

    def on_stop(self):
        self.log.info(f"Stopping BBMeanReversionStrategy for {self._instrument_id}")