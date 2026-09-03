from pydantic import BaseModel, Field
from typing import List, Optional
from agent.schemas import SyncReport, get_asset_sync_info


class SymbolItemSchema(BaseModel):
    symbol: str
    name: Optional[str] = None
    description: Optional[str] = None
    asset_class: Optional[str] = None
    venue: Optional[str] = None
    currency: Optional[str] = None
    sec_type: Optional[str] = None


class SymbolsSchema(BaseModel):
    symbols: List[SymbolItemSchema]

    @classmethod
    def from_group(cls, group) -> "SymbolsSchema":
        return cls(symbols=[
            SymbolItemSchema(
                symbol=code,
                asset_class=group.asset_class,
                venue=group.venue,
                currency=group.currency
            )
            for code in group.get_codes()
        ])

    def sync_model(self, instance) -> dict:
        from argo.models import Instrument, IBContract, InstrumentGroup, AssetClass
        from argo.instruments.search import InteractiveBrokersSearchService, ASSET_CLASS_TO_SEC_TYPE

        group = instance if isinstance(instance, InstrumentGroup) else None
        search_service = InteractiveBrokersSearchService()

        created_reports = []
        existing_reports = []
        skipped_reports = []

        for item in self.symbols:
            code = item.symbol.strip().upper()
            if not code:
                continue

            asset_class = item.asset_class or (group.asset_class if group else AssetClass.EQUITY)
            venue = item.venue or (group.venue if group else 'SMART')
            currency = item.currency or (group.currency if group else 'USD')
            sec_type = item.sec_type or ASSET_CLASS_TO_SEC_TYPE.get(asset_class, 'STK')

            matches = search_service.search(query=code, sec_type=sec_type, currency=currency)
            match = next((m for m in matches if m.symbol == code), None)
            if not match:
                skipped_reports.append({
                    'symbol': code,
                    'status': 'skipped',
                    'reason': 'Not found on Interactive Brokers'
                })
                continue

            contract_venue = item.venue or (group.venue if group else (match.primary_exchange or match.exchange or 'SMART'))
            contract_asset_class = match.asset_class or asset_class
            contract_currency = match.currency or currency

            instrument, created = Instrument.objects.get_or_create(
                symbol=match.symbol,
                venue=contract_venue,
                asset_class=contract_asset_class,
                defaults={
                    'currency': contract_currency,
                    'is_active': True,
                }
            )

            IBContract.objects.update_or_create(
                instrument=instrument,
                defaults={
                    'con_id': match.con_id if match.con_id > 0 else None,
                    'sec_type': match.sec_type,
                    'exchange': match.exchange or contract_venue,
                    'primary_exchange': match.primary_exchange,
                    'local_symbol': match.local_symbol,
                    'trading_class': match.trading_class,
                }
            )

            if group:
                instrument.groups.add(group)

            report = get_asset_sync_info(instrument, created)
            if created:
                created_reports.append(report)
            else:
                existing_reports.append(report)

        if group and (created_reports or existing_reports):
            all_codes = sorted(set(group.get_codes() + [
                r['name'] for r in created_reports + existing_reports
            ]))
            group.symbols = ", ".join(all_codes)
            group.save(update_fields=['symbols', 'updated_at'])

        return {
            'created': created_reports,
            'existing': existing_reports,
            'skipped': skipped_reports,
            'total_created': len(created_reports),
            'total_skipped': len(skipped_reports),
        }


class StrategyInstanceItemSchema(BaseModel):
    strategy: str
    symbol: str
    venue: Optional[str] = "SMART"
    asset_class: Optional[str] = None
    currency: Optional[str] = "USD"
    description: Optional[str] = None
    params: Optional[dict] = {}
    is_active: bool = True


class StrategyInstancesSchema(BaseModel):
    instances: List[StrategyInstanceItemSchema]

    def sync_model(self, portfolio) -> dict:
        from django.db.models import Q
        from argo.models import Strategy, Instrument, StrategyInstance, AssetClass
        from argo.instruments.search import InteractiveBrokersSearchService, ASSET_CLASS_TO_SEC_TYPE

        created_reports = []
        existing_reports = []
        skipped_reports = []
        search_service = InteractiveBrokersSearchService()

        for item in self.instances:
            strat_query = item.strategy.strip()
            strategy_obj = Strategy.objects.filter(
                Q(name__iexact=strat_query) | Q(class_path__iexact=strat_query) | Q(name__icontains=strat_query)
            ).first()

            if not strategy_obj:
                skipped_reports.append({
                    'item': f"{item.strategy} @ {item.symbol}",
                    'status': 'skipped',
                    'reason': f"Strategy '{item.strategy}' not found in registered strategies."
                })
                continue

            symbol_code = item.symbol.strip().upper()
            venue = item.venue or "SMART"
            asset_class = item.asset_class or AssetClass.EQUITY
            currency = item.currency or "USD"

            instrument = Instrument.objects.filter(symbol=symbol_code, venue=venue).first()
            if not instrument:
                try:
                    sec_type = ASSET_CLASS_TO_SEC_TYPE.get(asset_class, 'STK')
                    matches = search_service.search(query=symbol_code, sec_type=sec_type, currency=currency)
                    match = next((m for m in matches if m.symbol == symbol_code), None)
                    if match:
                        contract_venue = venue or match.primary_exchange or match.exchange or "SMART"
                        instrument, _ = Instrument.objects.get_or_create(
                            symbol=match.symbol,
                            venue=contract_venue,
                            asset_class=match.asset_class,
                            defaults={'currency': match.currency or currency, 'is_active': True}
                        )
                except Exception:
                    pass

            if not instrument:
                instrument, _ = Instrument.objects.get_or_create(
                    symbol=symbol_code,
                    venue=venue,
                    asset_class=asset_class,
                    defaults={'currency': currency, 'is_active': True}
                )

            instance_obj, created = StrategyInstance.objects.update_or_create(
                portfolio=portfolio,
                strategy_model=strategy_obj,
                instrument=instrument,
                defaults={
                    'description': item.description or "",
                    'params': item.params or {},
                    'is_active': item.is_active,
                }
            )

            report = get_asset_sync_info(instance_obj, created)
            if created:
                created_reports.append(report)
            else:
                existing_reports.append(report)

        return {
            'created': created_reports,
            'existing': existing_reports,
            'skipped': skipped_reports,
            'total_created': len(created_reports),
            'total_skipped': len(skipped_reports),
        }


class StrategyInstanceOptimizeSchema(BaseModel):
    strategy: Optional[str] = Field(None, description="Exact name or class path of the trading strategy.")
    symbol: str = Field(..., description="The instrument symbol code (e.g. 'AAPL', 'EURUSD', 'NVDA', 'SPY').")
    venue: Optional[str] = Field("SMART", description="Exchange / venue (e.g. 'SMART', 'IDEALPRO', 'CME').")
    asset_class: Optional[str] = Field(None, description="Asset class ('EQUITY', 'FX', 'CRYPTO', 'FUTURE', 'OPTION').")
    currency: Optional[str] = Field("USD", description="Currency (e.g. 'USD', 'EUR').")
    description: Optional[str] = Field(None, description="Trading rationale and parameter optimization summary.")
    params: dict = Field(default_factory=dict, description="Dictionary of optimized strategy parameters.")
    is_active: bool = Field(True, description="Whether the instance is active.")

    def sync_model(self, instance) -> dict:
        from django.db.models import Q
        from argo.models import Strategy, Instrument, AssetClass

        if self.strategy:
            strat_query = self.strategy.strip()
            strat_obj = Strategy.objects.filter(
                Q(name__iexact=strat_query) | Q(class_path__iexact=strat_query) | Q(name__icontains=strat_query)
            ).first()
            if strat_obj:
                instance.strategy_model = strat_obj

        symbol_code = self.symbol.strip().upper()
        venue = self.venue or "SMART"
        asset_class = self.asset_class or AssetClass.EQUITY
        currency = self.currency or "USD"

        instrument = self._resolve_instrument(symbol_code, venue, asset_class, currency)
        instance.instrument = instrument

        # Populate and merge default strategy parameters with optimized params
        defaults = self._get_default_strategy_params(instance.strategy_model)
        merged_params = {**defaults, **(self.params or {})}
        instance.params = merged_params

        if self.description:
            instance.description = self.description
        instance.is_active = self.is_active
        instance.save()

        report = get_asset_sync_info(instance, created=False)
        return {
            'instance_id': instance.id,
            'strategy': str(instance.strategy_model),
            'instrument': str(instance.instrument),
            'params': instance.params,
            'report': report,
        }

    def _get_default_strategy_params(self, strategy_model) -> dict:
        """Extracts default parameters from the strategy Config class."""
        if not strategy_model or not strategy_model.class_path:
            return {}
        try:
            import importlib
            module_path, class_name = strategy_model.class_path.rsplit(".", 1)
            module = importlib.import_module(module_path)
            config_class = getattr(module, f"{class_name}Config", None)
            if not config_class:
                return {}
            defaults = {}
            if hasattr(config_class, "__annotations__"):
                for field_name in config_class.__annotations__:
                    if field_name not in ["instrument_id", "bar_type"] and hasattr(config_class, field_name):
                        defaults[field_name] = getattr(config_class, field_name)
            return defaults
        except Exception:
            return {}

    def _resolve_instrument(self, symbol_code: str, venue: str, asset_class: str, currency: str):
        from argo.models import Instrument
        from argo.instruments.search import InteractiveBrokersSearchService, ASSET_CLASS_TO_SEC_TYPE

        instrument = Instrument.objects.filter(symbol=symbol_code, venue=venue).first()
        if instrument:
            return instrument

        search_service = InteractiveBrokersSearchService()
        try:
            sec_type = ASSET_CLASS_TO_SEC_TYPE.get(asset_class, 'STK')
            matches = search_service.search(query=symbol_code, sec_type=sec_type, currency=currency)
            match = next((m for m in matches if m.symbol == symbol_code), None)
            if match:
                contract_venue = venue or match.primary_exchange or match.exchange or "SMART"
                instrument, _ = Instrument.objects.get_or_create(
                    symbol=match.symbol,
                    venue=contract_venue,
                    asset_class=match.asset_class or asset_class,
                    defaults={'currency': match.currency or currency, 'is_active': True}
                )
                return instrument
        except Exception:
            pass

        instrument, _ = Instrument.objects.get_or_create(
            symbol=symbol_code,
            venue=venue,
            asset_class=asset_class,
            defaults={'currency': currency, 'is_active': True}
        )
        return instrument