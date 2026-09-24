from django.contrib import admin
from django.shortcuts import redirect
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from django.utils.html import format_html
from unfold.admin import ModelAdmin, StackedInline, TabularInline
from unfold.decorators import action
from simple_history.admin import SimpleHistoryAdmin
from agent.admin_utils import AjaxTaskModelAdmin, ModelActionsAdminMixin
from agent.sections import AjaxSectionAdminMixin, MessageHistorySection

from .models import (
    Account,
    Position,
    Strategy,
    Portfolio,
    StrategyInstance,
    Backtest,
    HistoricalData,
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
    inlines = []

    def instance_count(self, obj):
        if hasattr(obj, 'strategy_instances'):
            return obj.strategy_instances.count()
        return 0
    instance_count.short_description = _("Instances")

    def group_count(self, obj):
        return obj.instrument_groups.count()
    group_count.short_description = _("Groups")




class BacktestInline(TabularInline):
    model = Backtest
    extra = 0
    fields = ('name', 'start_date', 'end_date', 'total_pnl', 'return_pct', 'sharpe_ratio', 'max_drawdown_pct', 'win_rate', 'total_trades', 'last_tasks')
    readonly_fields = ('total_pnl', 'return_pct', 'sharpe_ratio', 'max_drawdown_pct', 'win_rate', 'total_trades', 'last_tasks')
    show_change_link = True


@admin.register(StrategyInstance)
class StrategyInstanceAdmin(SimpleHistoryAdmin, AjaxSectionAdminMixin, AjaxTaskModelAdmin, ModelAdmin):
    list_display = ('strategy_model', 'instrument', 'is_active', 'description', 'last_tasks')
    list_filter = ('is_active', 'strategy_model')
    search_fields = ('instrument__symbol', 'instrument__venue', 'strategy_model__name', 'description')
    autocomplete_fields = ('strategy_model', 'instrument')
    list_sections = [MessageHistorySection]
    inlines = [BacktestInline]


@admin.register(HistoricalData)
class HistoricalDataAdmin(AjaxSectionAdminMixin, AjaxTaskModelAdmin, ModelAdmin):
    list_display = ('instrument', 'bar_type', 'start_date', 'end_date', 'bar_count', 'source', 'created_at', 'last_tasks')
    list_filter = ('bar_type', 'instrument__asset_class')
    search_fields = ('instrument__symbol', 'bar_type', 'catalog_path')
    autocomplete_fields = ('instrument',)
    readonly_fields = ('created_at', 'updated_at', 'catalog_path', 'source', 'last_tasks')
    actions = ['load_data_action']

    @admin.action(description=_("Load historical data (create Parquet catalog)"))
    def load_data_action(self, request, queryset):
        count = 0
        for item in queryset:
            item.load_data(as_task=True, owner=request.user)
            count += 1
        self.message_user(request, _(f"Triggered catalog load task for {count} dataset(s)."))


@admin.register(Backtest)
class BacktestAdmin(SimpleHistoryAdmin, AjaxSectionAdminMixin, AjaxTaskModelAdmin, ModelAdmin):
    list_display = ('__str__', 'strategy_instance', 'is_data_covered', 'total_pnl', 'return_pct', 'sharpe_ratio', 'max_drawdown_pct', 'win_rate', 'total_trades', 'last_tasks')
    list_filter = ('optimization_objective', 'strategy_instance__strategy_model')
    search_fields = ('name', 'strategy_instance__instrument__symbol', 'strategy_instance__strategy_model__name')
    autocomplete_fields = ('strategy_instance',)
    list_sections = [MessageHistorySection]
    actions = ['apply_best_params_action', 'load_data_action']

    @admin.display(boolean=True, description=_("Data Covered"))
    def is_data_covered(self, obj):
        return obj.is_covered()

    @admin.action(description=_("Load historical data for selected backtests"))
    def load_data_action(self, request, queryset):
        count = 0
        for bt in queryset:
            bt.load_data()
            count += 1
        self.message_user(request, _(f"Checked and loaded historical data for {count} backtest(s)."))

    @admin.action(description=_("Apply winning parameters to StrategyInstance"))
    def apply_best_params_action(self, request, queryset):
        count = 0
        for bt in queryset:
            if bt.best_params:
                bt.apply_best_params_to_instance()
                count += 1
        self.message_user(request, _(f"Applied optimal parameters from {count} backtest(s) to StrategyInstance(s)."))




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
class InstrumentGroupAdmin(ModelActionsAdminMixin, SimpleHistoryAdmin, AjaxSectionAdminMixin, AjaxTaskModelAdmin, ModelAdmin):
    list_display = ('name', 'code', 'symbol_count', 'instrument_count', 'is_active', 'last_tasks')
    list_filter = ('is_active',)
    search_fields = ('name', 'code', 'description')
    actions = ['preview_codes_action']
    actions_row = [
        'search_and_create_instruments_row_action',
        'preview_codes_row_action',
        'populate_symbols_from_ib_row_action',
        'view_instruments_row_action',
    ]
    readonly_fields = ('instruments_link',)
    list_sections = [MessageHistorySection]
    list_refresh = ['instrument_count', 'symbol_count']

    def symbol_count(self, obj):
        return len(obj.get_codes())
    symbol_count.short_description = _("Symbols")

    def instrument_count(self, obj):
        count = obj.instruments.count()
        url = reverse("admin:argo_instrument_changelist") + f"?group={obj.id}"
        return format_html('<a href="{}" class="font-medium text-primary-600 hover:underline">{}</a>', url, count)
    instrument_count.short_description = _("Instruments")

    def instruments_link(self, obj):
        if not obj or not obj.pk:
            return "-"
        count = obj.instruments.count()
        url = reverse("admin:argo_instrument_changelist") + f"?group={obj.id}"
        return format_html(
            '<a href="{}" class="font-medium text-primary-600 hover:underline">{} ({} {})</a>',
            url,
            _("View Instruments"),
            count,
            _("total")
        )
    instruments_link.short_description = _("Linked Instruments")

    @action(description=_("View Instruments"), icon="list")
    def view_instruments_row_action(self, request, object_id):
        return redirect(reverse("admin:argo_instrument_changelist") + f"?group={object_id}")

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

    @action(description=_("Search IB & Create Instruments"), icon="search")
    def search_and_create_instruments_row_action(self, request, object_id):
        group = self.get_object(request, object_id)
        if group:
            task = group.search_and_create_instruments(as_task=True, owner=request.user)
            if task:
                self.message_user(
                    request,
                    _("Task %(task_id)s scheduled to search IB and create instruments for group '%(name)s'.") % {
                        "task_id": task.id,
                        "name": group.name,
                    }
                )
            else:
                created, total = group.search_and_create_instruments()
                self.message_user(
                    request,
                    _("Group '%(name)s': %(created)d new instrument(s) created, %(total)d processed via IB.") % {
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


class InstrumentGroupFilter(admin.SimpleListFilter):
    title = _("Group")
    parameter_name = "group"

    def lookups(self, request, model_admin):
        return [(g.id, f"{g.name} ({g.code})") for g in InstrumentGroup.objects.all().order_by("name")]

    def queryset(self, request, queryset):
        val = self.value() or request.GET.get("groups__id__exact")
        if val:
            return queryset.filter(groups__id=val).distinct()
        return queryset


@admin.register(Instrument)
class InstrumentAdmin(ModelAdmin):
    list_display = ('symbol', 'venue', 'asset_class', 'currency', 'display_groups', 'price_precision', 'lot_size', 'is_active')
    list_filter = (InstrumentGroupFilter, 'asset_class', 'venue', 'currency', 'is_active')
    search_fields = ('symbol', 'venue')
    filter_horizontal = ('groups',)
    inlines = [IBContractInline]

    def display_groups(self, obj):
        groups = obj.groups.all()
        if not groups:
            return "-"
        links = [
            format_html(
                '<a href="{}" class="font-medium text-primary-600 hover:underline">{}</a>',
                reverse("admin:argo_instrument_changelist") + f"?group={g.id}",
                g.name
            )
            for g in groups
        ]
        from django.utils.safestring import mark_safe
        return mark_safe(", ".join(links))
    display_groups.short_description = _("Groups")


@admin.register(IBContract)
class IBContractAdmin(ModelAdmin):
    list_display = ('instrument', 'sec_type', 'exchange', 'con_id', 'expiration', 'strike', 'option_right')
    list_filter = ('sec_type', 'exchange', 'option_right')
    search_fields = ('instrument__symbol', 'con_id', 'local_symbol')
    autocomplete_fields = ('instrument',)


