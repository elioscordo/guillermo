from pydantic import BaseModel
from typing import List, Optional


class SyncReport(dict):
    def __init__(self, name, instance, created, edited, fields_edited):
        super().__init__({
            'name': name,
            'instance': instance,
            'created': created,
            'edited': edited,
            'fields_edited': fields_edited
        })
        self.name = name
        self.instance = instance
        self.created = created
        self.edited = edited
        self.fields_edited = fields_edited


def get_asset_sync_info(instance, created):
    fields_edited = []
    if not created and hasattr(instance, 'history'):
        try:
            latest = instance.history.first()
            if latest:
                prev = latest.prev_record
                if prev:
                    delta = latest.diff_against(prev)
                    fields_edited = [change.field for change in delta.changes]
        except Exception:
            pass
    
    return SyncReport(
        name=getattr(instance, 'name', getattr(instance, 'symbol', str(instance))),
        instance=instance,
        created=created,
        edited=not created and len(fields_edited) > 0,
        fields_edited=fields_edited
    )


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