from django.contrib import admin
from django.shortcuts import redirect
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from unfold.admin import ModelAdmin, StackedInline
from unfold.decorators import action
from simple_history.admin import SimpleHistoryAdmin
from agent.admin_utils import AjaxTaskModelAdmin
from agent.sections import AjaxSectionAdminMixin, MessageHistorySection

from .models import (
    Account,
    Position,
    Strategy,
    Portfolio,
    StrategyInstance,
    Scanner,
    Signal,
    Recommendation,
    InstrumentGroup,
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
    autocomplete_fields = ('strategy_model', 'instrument')


@admin.register(Portfolio)
class PortfolioAdmin(SimpleHistoryAdmin, AjaxSectionAdminMixin, AjaxTaskModelAdmin, ModelAdmin):
    list_display = ('name', 'is_active', 'instance_count', 'group_count', 'description', 'last_tasks')
    list_filter = ('is_active', 'instrument_groups')
    search_fields = ('name', 'description')
    autocomplete_fields = ('instrument_groups',)
    list_sections = [MessageHistorySection]
    list_refresh = ['instance_count', 'group_count']
    inlines = [StrategyInstanceInline]

    def instance_count(self, obj):
        return obj.strategy_instances.count()
    instance_count.short_description = _("Instances")

    def group_count(self, obj):
        return obj.instrument_groups.count()
    group_count.short_description = _("Groups")




@admin.register(StrategyInstance)
class StrategyInstanceAdmin(ModelAdmin):
    list_display = ('portfolio', 'strategy_model', 'instrument', 'is_active', 'description')
    list_filter = ('is_active', 'portfolio', 'strategy_model')
    search_fields = ('instrument__symbol', 'instrument__venue', 'portfolio__name', 'strategy_model__name', 'description')
    autocomplete_fields = ('portfolio', 'strategy_model', 'instrument')



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


@admin.register(InstrumentGroup)
class InstrumentGroupAdmin(SimpleHistoryAdmin, AjaxSectionAdminMixin, AjaxTaskModelAdmin, ModelAdmin):
    list_display = ('name', 'code', 'asset_class', 'venue', 'currency', 'instrument_count', 'is_active', 'last_tasks')
    list_filter = ('asset_class', 'venue', 'currency', 'is_active')
    search_fields = ('name', 'code', 'description')
    actions = ['preview_codes_action', 'create_instruments_action']
    actions_row = ['preview_codes_row_action', 'populate_symbols_from_ib_row_action', 'create_instruments_row_action']
    list_sections = [MessageHistorySection]
    list_refresh = ['instrument_count']

    def instrument_count(self, obj):
        return obj.instruments.count()
    instrument_count.short_description = _("Instruments")

    @action(description=_("Populate from IB (via query)"), icon="search")
    def populate_symbols_from_ib_row_action(self, request, object_id):
        group = self.get_object(request, object_id)
        if group:
            query = group.code or group.name
            try:
                symbols = group.populate_symbols_from_ib(query=query, append=True)
                self.message_user(
                    request,
                    _("Group '%(name)s': populated %(count)d symbol(s) from IB -> %(symbols)s") % {
                        "name": group.name,
                        "count": len(symbols),
                        "symbols": ", ".join(symbols[:15]) + ("..." if len(symbols) > 15 else "")
                    }
                )
            except Exception as e:
                self.message_user(request, _("IB search failed: %(error)s") % {"error": str(e)}, level="error")
        return redirect(reverse("admin:argo_instrumentgroup_changelist"))


    @action(description=_("Preview codes for selected groups"), icon="visibility")
    def preview_codes_action(self, request, queryset):
        for group in queryset:
            codes = group.get_codes()
            self.message_user(
                request,
                _("Group '%(name)s' (%(code)s): found %(count)d symbol(s) -> %(symbols)s") % {
                    "name": group.name,
                    "code": group.code,
                    "count": len(codes),
                    "symbols": ", ".join(codes[:15]) + ("..." if len(codes) > 15 else "")
                }
            )

    @action(description=_("Create/Sync instruments for selected groups"), icon="add_circle")
    def create_instruments_action(self, request, queryset):
        total_created, total_synced = 0, 0
        for group in queryset:
            created, total = group.create_instruments()
            total_created += created
            total_synced += total
        self.message_user(
            request,
            _("Processed %(groups)d group(s): %(created)d new instruments created, %(total)d synchronized.") % {
                "groups": queryset.count(),
                "created": total_created,
                "total": total_synced,
            }
        )

    @action(description=_("Preview Codes"), icon="visibility")
    def preview_codes_row_action(self, request, object_id):
        group = self.get_object(request, object_id)
        if group:
            codes = group.get_codes()
            self.message_user(
                request,
                _("Group '%(name)s': %(count)d symbol(s) -> %(symbols)s") % {
                    "name": group.name,
                    "count": len(codes),
                    "symbols": ", ".join(codes[:20]) + ("..." if len(codes) > 20 else "")
                }
            )
        return redirect(reverse("admin:argo_instrumentgroup_changelist"))

    @action(description=_("Create Instruments"), icon="add_circle")
    def create_instruments_row_action(self, request, object_id):
        group = self.get_object(request, object_id)
        if group:
            created, total = group.create_instruments()
            self.message_user(
                request,
                _("Group '%(name)s': %(created)d new instrument(s) created, %(total)d synchronized.") % {
                    "name": group.name,
                    "created": created,
                    "total": total
                }
            )
        return redirect(reverse("admin:argo_instrumentgroup_changelist"))


class IBContractInline(StackedInline):
    model = IBContract
    extra = 0
    can_delete = False


@admin.register(Instrument)
class InstrumentAdmin(ModelAdmin):
    list_display = ('symbol', 'venue', 'asset_class', 'currency', 'price_precision', 'lot_size', 'is_active')
    list_filter = ('groups', 'asset_class', 'venue', 'currency', 'is_active')
    search_fields = ('symbol', 'venue')
    filter_horizontal = ('groups',)
    inlines = [IBContractInline]


@admin.register(IBContract)
class IBContractAdmin(ModelAdmin):
    list_display = ('instrument', 'sec_type', 'exchange', 'con_id', 'expiration', 'strike', 'option_right')
    list_filter = ('sec_type', 'exchange', 'option_right')
    search_fields = ('instrument__symbol', 'con_id', 'local_symbol')
    autocomplete_fields = ('instrument',)


