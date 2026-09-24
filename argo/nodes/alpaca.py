from nautilus_trader.config import LiveNodeConfig
from nautilus_trader.live.node import LiveNode
from nautilus_trader.adapters. import AlpacaLiveDataClientFactory
from nautilus_trader.adapters.alpaca.config import AlpacaDataClientConfig
from nautilus_trader.adapters.interactive_brokers.factories import InteractiveBrokersLiveExecClientFactory
from nautilus_trader.adapters.interactive_brokers.config import InteractiveBrokersExecClientConfig

# Configure Alpaca for data (Free or $9/mo SIP)
data_config = AlpacaDataClientConfig(
    api_key="YOUR_ALPACA_KEY",
    secret_key="YOUR_ALPACA_SECRET",
    # Set to 'sip' if on paid tier, or 'iex' for free
)

# Configure IB for order execution
exec_config = InteractiveBrokersExecClientConfig(
    host="127.0.0.1",
    port=7497, # TWS paper or 4002 for IB Gateway
    client_id=1,
)

node_config = LiveNodeConfig(
    data_clients={"ALPACA": data_config},
    exec_clients={"IB": exec_config},
)