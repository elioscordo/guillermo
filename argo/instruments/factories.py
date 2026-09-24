from datetime import datetime, timezone
from typing import Optional

from ibapi.contract import Contract as IbRawContract
from nautilus_trader.adapters.interactive_brokers.common import IBContract as NautilusIBContract
from nautilus_trader.model.currencies import Currency
from nautilus_trader.model.enums import AssetClass as NautilusAssetClass
from nautilus_trader.model.enums import OptionKind
from nautilus_trader.model.identifiers import InstrumentId, Symbol, Venue
from nautilus_trader.model.instruments import (
    CurrencyPair,
    Equity,
    FuturesContract,
    Instrument as NautilusInstrument,
    OptionContract,
)
from nautilus_trader.model.objects import Price, Quantity

from argo.models import AssetClass, Instrument, OptionRight


class IBContractAdapter:
    """
    Adapter converting Django Instrument/IBContract models into Nautilus/IB API contracts.
    """

    @staticmethod
    def to_nautilus_ib_contract(model: Instrument) -> NautilusIBContract:
        """Builds Nautilus Trader's IBContract configuration object."""
        ib = getattr(model, "ib_contract", None)
        sec_type = ib.sec_type if ib else "STK"
        exchange = ib.exchange if ib else model.venue

        kwargs = {
            "secType": sec_type,
            "symbol": model.symbol,
            "currency": model.currency,
            "exchange": exchange,
        }

        if ib:
            if ib.con_id:
                kwargs["conId"] = ib.con_id
            if ib.primary_exchange:
                kwargs["primaryExchange"] = ib.primary_exchange
            if ib.local_symbol:
                kwargs["localSymbol"] = ib.local_symbol
            if ib.trading_class:
                kwargs["tradingClass"] = ib.trading_class
            if ib.expiration:
                kwargs["lastTradeDateOrContractMonth"] = ib.expiration.strftime("%Y%m%d")
            if ib.strike:
                kwargs["strike"] = float(ib.strike)
            if ib.option_right:
                kwargs["right"] = "C" if ib.option_right == OptionRight.CALL else "P"
            if model.multiplier != 1:
                kwargs["multiplier"] = str(int(model.multiplier))

        return NautilusIBContract(**kwargs)

    @staticmethod
    def to_raw_ibapi_contract(model: Instrument) -> IbRawContract:
        """Builds official ibapi.contract.Contract for raw TWS/Gateway queries."""
        ib = getattr(model, "ib_contract", None)
        contract = IbRawContract()
        contract.symbol = model.symbol
        contract.currency = model.currency
        contract.secType = ib.sec_type if ib else "STK"
        contract.exchange = ib.exchange if ib else model.venue

        if ib:
            if ib.con_id:
                contract.conId = ib.con_id
            if ib.primary_exchange:
                contract.primaryExchange = ib.primary_exchange
            if ib.local_symbol:
                contract.localSymbol = ib.local_symbol
            if ib.trading_class:
                contract.tradingClass = ib.trading_class
            if ib.expiration:
                contract.lastTradeDateOrContractMonth = ib.expiration.strftime("%Y%m%d")
            if ib.strike:
                contract.strike = float(ib.strike)
            if ib.option_right:
                contract.right = "C" if ib.option_right == OptionRight.CALL else "P"
            if model.multiplier != 1:
                contract.multiplier = str(int(model.multiplier))

        return contract


class NautilusInstrumentFactory:
    """
    Factory creating Nautilus domain Instrument objects from Django models.
    """

    @classmethod
    def create(cls, model: Instrument) -> NautilusInstrument:
        dispatch = {
            AssetClass.EQUITY: cls._build_equity,
            AssetClass.FUTURE: cls._build_future,
            AssetClass.OPTION: cls._build_option,
            AssetClass.FX: cls._build_currency_pair,
        }
        builder = dispatch.get(model.asset_class, cls._build_equity)
        return builder(model)

    @staticmethod
    def _create_instrument_id(model: Instrument) -> InstrumentId:
        return InstrumentId(
            symbol=Symbol(model.symbol),
            venue=Venue(model.venue),
        )

    @classmethod
    def _build_equity(cls, model: Instrument) -> Equity:
        return Equity(
            instrument_id=cls._create_instrument_id(model),
            raw_symbol=Symbol(model.symbol),
            currency=Currency.from_str(model.currency),
            price_precision=model.price_precision,
            price_increment=Price(model.price_increment, precision=model.price_precision),
            lot_size=Quantity(model.lot_size, precision=model.size_precision),
            ts_event=0,
            ts_init=0,
        )

    @classmethod
    def _build_future(cls, model: Instrument) -> FuturesContract:
        ib = getattr(model, "ib_contract", None)
        raw_sym = ib.local_symbol if (ib and ib.local_symbol) else model.symbol
        exp_ns = cls._calc_expiration_ns(ib.expiration if ib else None)

        return FuturesContract(
            instrument_id=cls._create_instrument_id(model),
            raw_symbol=Symbol(raw_sym),
            asset_class=NautilusAssetClass.COMMODITY,
            currency=Currency.from_str(model.currency),
            price_precision=model.price_precision,
            price_increment=Price(model.price_increment, precision=model.price_precision),
            multiplier=Quantity(model.multiplier, precision=0),
            lot_size=Quantity(model.lot_size, precision=model.size_precision),
            underlying=model.symbol,
            activation_ns=0,
            expiration_ns=exp_ns,
            ts_event=0,
            ts_init=0,
        )

    @classmethod
    def _build_option(cls, model: Instrument) -> OptionContract:
        ib = getattr(model, "ib_contract", None)
        raw_sym = ib.local_symbol if (ib and ib.local_symbol) else model.symbol
        kind = OptionKind.CALL if (ib and ib.option_right == OptionRight.CALL) else OptionKind.PUT
        strike = ib.strike if (ib and ib.strike) else 0.0
        exp_ns = cls._calc_expiration_ns(ib.expiration if ib else None)

        return OptionContract(
            instrument_id=cls._create_instrument_id(model),
            raw_symbol=Symbol(raw_sym),
            asset_class=NautilusAssetClass.EQUITY,
            currency=Currency.from_str(model.currency),
            price_precision=model.price_precision,
            price_increment=Price(model.price_increment, precision=model.price_precision),
            multiplier=Quantity(model.multiplier, precision=0),
            lot_size=Quantity(model.lot_size, precision=model.size_precision),
            underlying=model.symbol,
            option_kind=kind,
            strike_price=Price(strike, precision=model.price_precision),
            activation_ns=0,
            expiration_ns=exp_ns,
            ts_event=0,
            ts_init=0,
        )

    @classmethod
    def _build_currency_pair(cls, model: Instrument) -> CurrencyPair:
        quote = model.quote_currency or "USD"
        return CurrencyPair(
            instrument_id=cls._create_instrument_id(model),
            raw_symbol=Symbol(model.symbol),
            base_currency=Currency.from_str(model.currency),
            quote_currency=Currency.from_str(quote),
            price_precision=model.price_precision,
            size_precision=model.size_precision,
            price_increment=Price(model.price_increment, precision=model.price_precision),
            size_increment=Quantity(model.size_increment, precision=model.size_precision),
            lot_size=Quantity(model.lot_size, precision=model.size_precision),
            max_quantity=Quantity(100_000_000, precision=model.size_precision),
            min_quantity=Quantity(model.lot_size, precision=model.size_precision),
            max_price=Price(1_000_000, precision=model.price_precision),
            min_price=Price(model.price_increment, precision=model.price_precision),
            margin_init=0.0,
            margin_maint=0.0,
            maker_fee=0.0,
            taker_fee=0.0,
            ts_event=0,
            ts_init=0,
        )

    @staticmethod
    def _calc_expiration_ns(expiration_date) -> int:
        if not expiration_date:
            return 0
        dt = datetime.combine(expiration_date, datetime.min.time(), tzinfo=timezone.utc)
        return int(dt.timestamp() * 1_000_000_000)
