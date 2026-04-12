"""
Nautilus Trader + Interactive Brokers Trend Following Strategy
--------------------------------------------------------------
Prerequisites:
1. Nautilus Trader installed: pip install nautilus_trader
2. IB Gateway or TWS running and configured to accept API connections.
3. Enable "Download open orders on connection" in TWS/Gateway API settings.

Usage:
Update the `IB_ACCOUNT_ID` and `SYMBOL` variables below before running.
"""

import signal
import sys
from decimal import Decimal
from nautilus_trader.config import TradingNodeConfig
from nautilus_trader.adapters.interactive_brokers.config import (
    InteractiveBrokersDataClientConfig,
    InteractiveBrokersExecClientConfig,
    InteractiveBrokersInstrumentProviderConfig,
)
from nautilus_trader.adapters.interactive_brokers.factories import (
    InteractiveBrokersLiveDataClientFactory,
    InteractiveBrokersLiveExecClientFactory,
)
from nautilus_trader.config import (LoggingConfig,
    RiskEngineConfig,
)
from nautilus_trader.core.datetime import dt_to_unix_nanos
from nautilus_trader.indicators import     ExponentialMovingAverage
from nautilus_trader.live.node import TradingNode
from nautilus_trader.model.data import Bar, BarType
from nautilus_trader.model.enums import (
    AccountType,
    BarAggregation,
    OmsType,
    OrderSide,
    PriceType,
    TimeInForce,
)
from nautilus_trader.model.identifiers import InstrumentId, TraderId, Venue
from nautilus_trader.model.objects import Quantity
from nautilus_trader.trading.strategy import Strategy, StrategyConfig

# --- CONFIGURATION ---
IB_ACCOUNT_ID = "DU123456"  # REPLACE WITH YOUR IB ACCOUNT ID
IB_HOST = "127.0.0.1"
IB_PORT = 4002  # 7497 for TWS paper, 4002 for Gateway paper
CLIENT_ID = 1

SYMBOL = "EUR/USD"  # Example Forex pair
VENUE = "IB"
BAR_PERIOD = "1-MINUTE"  # Aggregation period

# --- STRATEGY ---
class EMATrendConfig(StrategyConfig):
    instrument_id: InstrumentId
    bar_type: BarType
    fast_ema_period: int = 10
    slow_ema_period: int = 20
    trade_size: Decimal = Decimal("20000")

class EMATrendStrategy(Strategy):
    def __init__(self, config: EMATrendConfig):
        super().__init__(config)
        
        # Initialize Indicators
        self.fast_ema = ExponentialMovingAverage(config.fast_ema_period)
        self.slow_ema = ExponentialMovingAverage(config.slow_ema_period)
        
        # State
        self.instrument = None

    def on_start(self):
        # Subscribe to bars for the instrument
        self.instrument = self.cache.instrument(self.config.instrument_id)
        if self.instrument:
            self.subscribe_bars(self.config.bar_type)
            self.log.info(f"Strategy started. Subscribed to {self.config.bar_type}")
        else:
            self.log.error(f"Could not find instrument: {self.config.instrument_id}")
            self.stop()

    def on_bar(self, bar: Bar):
        # Update indicators
        self.fast_ema.update(bar.close)
        self.slow_ema.update(bar.close)

        # Ensure indicators are ready
        if not self.fast_ema.initialized or not self.slow_ema.initialized:
            return

        # Log current state
        fast = self.fast_ema.value
        slow = self.slow_ema.value
        self.log.info(f"Price: {bar.close} | Fast EMA: {fast:.5f} | Slow EMA: {slow:.5f}")

        # Trading Logic: Crossover
        if fast > slow:
            self._check_long_entry()
        elif fast < slow:
            self._check_short_entry()

    def _check_long_entry(self):
        # If we have no position or we are short, go long
        current_position = self.cache.position(self.config.instrument_id)
        
        if not current_position:
            self._submit_order(OrderSide.BUY, self.config.trade_size)
        elif current_position.side == OrderSide.SELL:
            # Close short and flip to long (2x size or simple close then open)
            self.close_position(self.config.instrument_id)
            self._submit_order(OrderSide.BUY, self.config.trade_size)

    def _check_short_entry(self):
        # If we have no position or we are long, go short
        current_position = self.cache.position(self.config.instrument_id)

        if not current_position:
            self._submit_order(OrderSide.SELL, self.config.trade_size)
        elif current_position.side == OrderSide.BUY:
            self.close_position(self.config.instrument_id)
            self._submit_order(OrderSide.SELL, self.config.trade_size)

    def _submit_order(self, side: OrderSide, qty: Decimal):
        order = self.order_factory.market(
            instrument_id=self.config.instrument_id,
            order_side=side,
            quantity=Quantity.from_int(int(qty)),  # IB often requires integer lots for FX
            time_in_force=TimeInForce.GTC,
        )
        self.submit_order(order)
        self.log.info(f"Submitted {side} order for {qty} units.")

# --- MAIN EXECUTION ---
if __name__ == "__main__":
    # 1. Configure the Node
    node_config = TradingNodeConfig(
        trader_id=TraderId("IB-TREND-BOT-01"),
        logging=LoggingConfig(log_level="INFO")
    )
    
    node = TradingNode(config=node_config)

    # 2. Configure IB Connection
    ib_instrument_config = InteractiveBrokersInstrumentProviderConfig(
        load_ids=frozenset({f"{SYMBOL}.{VENUE}"})
    )
    
    data_config = InteractiveBrokersDataClientConfig(
        ibg_host="127.0.0.1",
        ibg_port=4002,
        ibg_client_id=1,
    )
    
    ib_exec_config = InteractiveBrokersExecClientConfig(
        gateway_host=IB_HOST,
        gateway_port=IB_PORT,
        client_id=CLIENT_ID,
        account_id=IB_ACCOUNT_ID,
    )

    # 3. Register Factories (Data & Execution)
    node.add_data_client_factory("IB", InteractiveBrokersLiveDataClientFactory)
    node.add_exec_client_factory("IB", InteractiveBrokersLiveExecClientFactory)
    node.build()

    # 4. Start the Node (Connects to IB)
    print("Starting Trading Node and connecting to IB...")
    node.stop() # Ensure clean state
    
    # Manually adding the factories usually requires the node to be running or configured
    # In the new Nautilus API, we often add the client instances or configure them via the node loop.
    # We will let the node manage the connection via the configs passed to factories.
    
    # Note: We must register the specific client instances after build or let the config handle it.
    # For this script, we assume the factory pattern handles the connection upon node start.
    
    # 5. Define Instrument and Bar Type
    # Note: Nautilus needs the Instrument definition. In live mode, we fetch it from IB.
    # We use a blocking call here to ensure connection before adding strategy.
    node.start()
    
    # Wait for connection (simple loop or manual wait)
    # Ideally, we use the instrument provider to load the instrument definition
    provider = node.instrument_provider("IB")
    print(f"Loading instrument {SYMBOL}...")
    
    # This might take a moment to fetch from TWS
    import time
    time.sleep(2) 
    
    # We manually create the ID to look up
    instr_id = InstrumentId(
        symbol=SYMBOL.replace("/", ""), # IB usually uses 'EURUSD' format internally for ID lookups or similar
        venue=Venue(VENUE)
    )
    
    # For the sake of this script, we will define the instrument ID string directly as Nautilus expects
    # e.g., "EURUSD.IB" or similar depending on the symbology.
    # We will use the standard ID format.
    instrument_id = InstrumentId.from_str(f"{SYMBOL.replace('/', '')}.{VENUE}")
    
    bar_type = BarType(
        instrument_id=instrument_id,
        bar_aggregation=BarAggregation.MINUTE,
        bar_period=1,
        price_type=PriceType.MID,
    )

    # 6. Instantiate and Add Strategy
    strategy_config = EMATrendConfig(
        instrument_id=instrument_id,
        bar_type=bar_type,
        trade_size=Decimal("20000"),
    )
    
    strategy = EMATrendStrategy(config=strategy_config)
    node.add_strategy(strategy)

    print("Strategy added. Press Ctrl+C to stop.")

    # 7. Keep running
    try:
        # Initial sleep to allow data subscription to kick in
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("Stopping node...")
        node.stop()
        sys.exit(0)