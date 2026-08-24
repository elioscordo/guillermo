from django.contrib import admin
from django.shortcuts import redirect
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from unfold.admin import ModelAdmin, StackedInline
from unfold.decorators import action

from .models import (
    Account,
    Position,
    Strategy,
    Portfolio,
    StrategyInstance,
    Scanner,
    Signal,
    Recommendation,
    Instrument,
    IBContract,
)
from .utils import load_strategies_from_package


@admin.register(Account)
class AccountAdmin(ModelAdmin):
    list_display = ('account_id', 'account_type', 'base_currency', 'balance_total', 'balance_free', 'balance_locked', 'is_reported', 'updated_at')
    list_filter = ('account_type', 'base_currency', 'is_reported')
    search_fields = ('account_id', 'account_type', 'base_currency')
    readonly_fields = ('updated_at',)


@admin.register(Position)
class PositionAdmin(ModelAdmin):
    list_display = ('account_id', 'instrument_id', 'side', 'status', 'quantity', 'avg_price', 'realized_pnl', 'unrealized_pnl', 'updated_at')
    list_filter = ('side', 'status')
    search_fields = ('account_id', 'instrument_id')
    readonly_fields = ('updated_at',)


@admin.register(Strategy)
class StrategyAdmin(ModelAdmin):
    list_display = ('name', 'class_path', 'description')
    search_fields = ('name', 'class_path')
    actions_list = ['load_strategies_from_package_action']

    @action(description=_("Load Strategies from Package"), icon="sync")
    def load_strategies_from_package_action(self, request):
        loaded = load_strategies_from_package("argo.strategies")
        self.message_user(
            request,
            _("Successfully loaded/synced %(count)d strategies from argo.strategies.") % {"count": len(loaded)}
        )
        return redirect(reverse("admin:argo_strategy_changelist"))


class StrategyInstanceInline(StackedInline):
    model = StrategyInstance
    extra = 0
    autocomplete_fields = ('strategy_model',)


@admin.register(Portfolio)
class PortfolioAdmin(ModelAdmin):
    list_display = ('name', 'is_active', 'description')
    list_filter = ('is_active',)
    search_fields = ('name', 'description')
    inlines = [StrategyInstanceInline]


@admin.register(StrategyInstance)
class StrategyInstanceAdmin(ModelAdmin):
    list_display = ('portfolio', 'strategy_model', 'instrument_id', 'is_active')
    list_filter = ('is_active', 'portfolio', 'strategy_model')
    search_fields = ('instrument_id', 'portfolio__name', 'strategy_model__name')
    autocomplete_fields = ('portfolio', 'strategy_model')


@admin.register(Scanner)
class ScannerAdmin(ModelAdmin):
    list_display = ('name', 'scanner_class_path', 'description')
    search_fields = ('name', 'scanner_class_path')


@admin.register(Signal)
class SignalAdmin(ModelAdmin):
    list_display = ('scanner', 'instrument_id', 'signal_type', 'status', 'confidence', 'generated_at')
    list_filter = ('signal_type', 'status', 'scanner')
    search_fields = ('instrument_id', 'scanner__name')
    autocomplete_fields = ('scanner',)
    readonly_fields = ('generated_at',)


@admin.register(Recommendation)
class RecommendationAdmin(ModelAdmin):
    list_display = ('signal', 'recommended_strategy', 'status', 'created_at')
    list_filter = ('status', 'recommended_strategy')
    search_fields = ('signal__instrument_id', 'recommended_strategy__name', 'justification')
    autocomplete_fields = ('signal', 'recommended_strategy')
    readonly_fields = ('created_at',)


class IBContractInline(StackedInline):
    model = IBContract
    extra = 0
    can_delete = False


@admin.register(Instrument)
class InstrumentAdmin(ModelAdmin):
    list_display = ('symbol', 'venue', 'asset_class', 'currency', 'price_precision', 'lot_size', 'is_active')
    list_filter = ('asset_class', 'venue', 'currency', 'is_active')
    search_fields = ('symbol', 'venue')
    inlines = [IBContractInline]


@admin.register(IBContract)
class IBContractAdmin(ModelAdmin):
    list_display = ('instrument', 'sec_type', 'exchange', 'con_id', 'expiration', 'strike', 'option_right')
    list_filter = ('sec_type', 'exchange', 'option_right')
    search_fields = ('instrument__symbol', 'con_id', 'local_symbol')
    autocomplete_fields = ('instrument',)

