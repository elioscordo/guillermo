from nautilus_trader.config import ImportableActorConfig
from nautilus_trader.model.data import Bar, BarType
from nautilus_trader.model.enums import OrderSide, TimeInForce
from nautilus_trader.trading.strategy import Strategy as NautilusStrategy


class BuyAndHoldConfig(ImportableActorConfig):
    """
    Configuration for baseline Buy and Hold benchmark strategy.
    """
    instrument_id: str
    bar_type: str
    trade_size: float = 100.0


class BuyAndHoldStrategy(NautilusStrategy):
    """
    Buy and Hold Strategy:
    - Buys on the very first received bar and holds until strategy stops.
    - Used as a benchmark baseline against all active alpha strategies.
    """

    def __init__(self, config: BuyAndHoldConfig):
        super().__init__(config=config)
        self.config = config
        self.position_open = False
        self._instrument_id = self.instrument_provider.get_instrument(self.config.instrument_id)
        self._bar_type = BarType.from_str(self.config.bar_type)

    def on_start(self):
        self.log.info(f"Starting BuyAndHoldStrategy benchmark for {self._instrument_id}")
        self.subscribe_data(self._instrument_id, self._bar_type)

    def on_bar(self, bar: Bar):
        if bar.instrument_id != self._instrument_id.id:
            return

        if not self.position_open:
            self.log.info(f"[{self._instrument_id}] Initial Buy and Hold entry at {bar.close}.")
            order = self.order_factory.market(self._instrument_id, OrderSide.BUY, self.config.trade_size, TimeInForce.GTC)
            self.submit_order(order)
            self.position_open = True

    def on_stop(self):
        self.log.info(f"Stopping BuyAndHoldStrategy for {self._instrument_id}")
