import re
from django.db import models
from django.conf import settings
from .utils import discover_strategies
from django.utils.translation import gettext_lazy as _
from simple_history.models import HistoricalRecords
from task.mixins import AfterSaveActionMixin
from task.models import TaskHolder
from agent.models import GetContentsMixin, Agent




class Account(models.Model):
    """
    Represents a trading account synchronized from NautilusTrader.
    """
    account_id = models.CharField(max_length=100, unique=True, help_text="Nautilus AccountId string.")
    account_type = models.CharField(max_length=50, blank=True, help_text="e.g. CASH, MARGIN, BETTING.")
    base_currency = models.CharField(max_length=10, blank=True, help_text="Base currency code (e.g. USD, EUR).")
    
    balance_total = models.DecimalField(max_digits=20, decimal_places=4, default=0.0)
    balance_free = models.DecimalField(max_digits=20, decimal_places=4, default=0.0)
    balance_locked = models.DecimalField(max_digits=20, decimal_places=4, default=0.0)
    
    balances = models.JSONField(default=dict, blank=True, help_text="Multi-currency balance breakdowns.")
    margins = models.JSONField(default=dict, blank=True, help_text="Margin usage details.")
    info = models.JSONField(default=dict, blank=True, help_text="Additional broker metadata.")
    
    is_reported = models.BooleanField(default=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['account_id']
        verbose_name = _('Account')
        verbose_name_plural = _('Accounts')

    def __str__(self):
        return f"{self.account_id} ({self.base_currency} {self.balance_total})"

    @classmethod
    def sync_from_nautilus(cls, nautilus_account):
        """
        Synchronizes a NautilusTrader Account instance or AccountState event to the database.
        """
        account_id = str(getattr(nautilus_account, "id", getattr(nautilus_account, "account_id", nautilus_account)))
        account_type = str(getattr(nautilus_account, "account_type", ""))
        base_currency = str(getattr(nautilus_account, "base_currency", ""))
        
        balances_dict = {}
        total_bal = 0.0
        free_bal = 0.0
        locked_bal = 0.0

        if hasattr(nautilus_account, "balances"):
            raw_balances = nautilus_account.balances() if callable(nautilus_account.balances) else nautilus_account.balances
            if isinstance(raw_balances, dict):
                for curr, bal in raw_balances.items():
                    curr_str = str(curr)
                    c_total = float(getattr(bal, "total", getattr(bal, "balance_total", 0.0)))
                    c_free = float(getattr(bal, "free", getattr(bal, "balance_free", 0.0)))
                    c_locked = float(getattr(bal, "locked", getattr(bal, "balance_locked", 0.0)))
                    balances_dict[curr_str] = {"total": c_total, "free": c_free, "locked": c_locked}
                    if not total_bal or curr_str == base_currency:
                        total_bal, free_bal, locked_bal = c_total, c_free, c_locked
            elif isinstance(raw_balances, list):
                for bal in raw_balances:
                    curr_str = str(getattr(bal, "currency", base_currency))
                    c_total = float(getattr(bal, "total", 0.0))
                    c_free = float(getattr(bal, "free", 0.0))
                    c_locked = float(getattr(bal, "locked", 0.0))
                    balances_dict[curr_str] = {"total": c_total, "free": c_free, "locked": c_locked}
                    if not total_bal or curr_str == base_currency:
                        total_bal, free_bal, locked_bal = c_total, c_free, c_locked

        if hasattr(nautilus_account, "balance_total"):
            b_total = getattr(nautilus_account, "balance_total", None)
            total_bal = float(b_total() if callable(b_total) else b_total) if b_total is not None else total_bal
        if hasattr(nautilus_account, "balance_free"):
            b_free = getattr(nautilus_account, "balance_free", None)
            free_bal = float(b_free() if callable(b_free) else b_free) if b_free is not None else free_bal
        if hasattr(nautilus_account, "balance_locked"):
            b_locked = getattr(nautilus_account, "balance_locked", None)
            locked_bal = float(b_locked() if callable(b_locked) else b_locked) if b_locked is not None else locked_bal

        margins_dict = {}
        if hasattr(nautilus_account, "margins"):
            raw_margins = nautilus_account.margins() if callable(nautilus_account.margins) else nautilus_account.margins
            if isinstance(raw_margins, dict):
                margins_dict = {str(k): float(v) if isinstance(v, (int, float)) else str(v) for k, v in raw_margins.items()}

        info_dict = {}
        if hasattr(nautilus_account, "info"):
            raw_info = nautilus_account.info
            info_dict = raw_info if isinstance(raw_info, dict) else {}

        instance, _ = cls.objects.update_or_create(
            account_id=account_id,
            defaults={
                "account_type": account_type,
                "base_currency": base_currency,
                "balance_total": total_bal,
                "balance_free": free_bal,
                "balance_locked": locked_bal,
                "balances": balances_dict,
                "margins": margins_dict,
                "info": info_dict,
            },
        )
        return instance


class Position(models.Model):
    class Side(models.TextChoices):
        LONG = 'LONG', 'Long'
        SHORT = 'SHORT', 'Short'

    class Status(models.TextChoices):
        OPEN = 'OPEN', 'Open'
        CLOSED = 'CLOSED', 'Closed'

    account_id = models.CharField(max_length=50)
    instrument_id = models.CharField(max_length=100)
    
    # Track BOTH direction and lifecycle status
    side = models.CharField(max_length=5, choices=Side.choices)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.OPEN)
    
    quantity = models.DecimalField(max_digits=18, decimal_places=6)
    avg_price = models.DecimalField(max_digits=18, decimal_places=6)
    realized_pnl = models.DecimalField(max_digits=18, decimal_places=4, default=0.0)
    unrealized_pnl = models.DecimalField(max_digits=18, decimal_places=4, default=0.0)
    
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.account_id} - {self.instrument_id}"



class Strategy(models.Model):
    """
    Represents a strategy class available in the system.
    """
    # Generate the choices list dynamically
    STRATEGY_CHOICES = discover_strategies()

    name = models.CharField(max_length=100, unique=True, help_text="A unique name for the strategy.")
    class_path = models.CharField(
        choices=STRATEGY_CHOICES,
        max_length=255,
        unique=True,
        help_text="Full Python path to the strategy class (e.g., 'argo.nautilus.strategies.EMACross')."
    )
    description = models.TextField(blank=True)

    def __str__(self):
        return self.name


class Portfolio(AfterSaveActionMixin, models.Model, GetContentsMixin, TaskHolder):
    """
    A collection of strategy instances to be run together.
    """
    TASK_TEXT_GENERATE = getattr(settings, 'TASK_TYPE_GENERATE_TEXT', 'generate_text')

    PRESET_SYNC_INSTANCES = "sync_instances"
    PRESET_CREATE_INSTANCES = "create_instances"

    ACTION_CREATE_INSTANCES = f"{TASK_TEXT_GENERATE}-preset-{PRESET_CREATE_INSTANCES}-target-description-schema-instances"
    ACTION_SYNC_INSTANCES = f"{TASK_TEXT_GENERATE}-preset-{PRESET_SYNC_INSTANCES}-target-description-schema-instances"

    ACTION_CHOICES = (
        (ACTION_CREATE_INSTANCES, _("Create instances from description")),
        (ACTION_SYNC_INSTANCES, _("Sync instances")),
    ) + getattr(settings, 'COMMON_TEXT_ACTION_CHOICES', ())

    AGENT_PRESETS = (
        (PRESET_CREATE_INSTANCES, _("Create instances")),
        (PRESET_SYNC_INSTANCES, _("Sync instances")),
    ) + getattr(settings, 'COMMON_TEXT_AGENT_PRESETS', ())

    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True)
    instrument_groups = models.ManyToManyField('InstrumentGroup', related_name='portfolios', blank=True)
    is_active = models.BooleanField(default=False, help_text="If active, this portfolio will be run by the trading node.")
    action = models.SlugField(_("action"), max_length=1024, choices=ACTION_CHOICES, null=True, blank=True)
    history = HistoricalRecords()

    class Meta:
        verbose_name = _('Portfolio')
        verbose_name_plural = _('Portfolios')
        ordering = ['name']

    def __str__(self):
        return self.name

    def get_contents(self, generate_self=True, preset=None):
        parts = []
        if preset in [self.PRESET_SYNC_INSTANCES, self.PRESET_CREATE_INSTANCES]:
            if self.name:
                parts.append(f"Portfolio Name: {self.name}")
            if self.description:
                parts.append(f"Portfolio Description: {self.description}")

            instances = self.strategy_instances.select_related('strategy_model', 'instrument').all()
            inst_lines = [
                f"- Strategy: {si.strategy_model.name} ({si.strategy_model.class_path}), Instrument: {si.instrument}, Active: {si.is_active}, Params: {si.params}"
                for si in instances
            ]
            parts.append(
                "### Existing Strategy Instances:\n" + ("\n".join(inst_lines) if inst_lines else "None")
            )

            # Provide available registered strategies in the system
            from argo.models import Strategy
            all_strats = Strategy.objects.all()
            if all_strats.exists():
                strat_lines = [
                    f"- Name: '{s.name}' | Class: '{s.class_path}' | Description: {s.description or 'N/A'}"
                    for s in all_strats
                ]
                parts.append("### Available Registered Strategies in System:\n" + "\n".join(strat_lines))
        else:
            parts = super().get_contents(generate_self=generate_self, preset=preset)

        groups = self.instrument_groups.all()
        if groups.exists():
            group_lines = [
                f"- Group: {g.name} ({g.code}), Asset Class: {g.asset_class}, Venue: {g.venue}, Symbols: {g.symbols}\n  Description: {g.description or 'No description'}"
                for g in groups
            ]
            parts.append("### Associated Instrument Groups:\n" + "\n".join(group_lines))

        return parts


    @classmethod
    def sync_from_node(cls, node):
        """
        Synchronizes the state of a Nautilus TradingNode to the database.

        This function creates or updates a Portfolio and its StrategyInstances
        based on the strategies running in the provided node.

        Args:
            node: An instance of nautilus_trader.live.node.TradingNode.
        """
        portfolio_name = node.config.trader_id
        portfolio, created = cls.objects.update_or_create(
            name=portfolio_name,
            defaults={'description': f"Portfolio synced from node '{portfolio_name}'."}
        )
        if created:
            print(f"Created portfolio '{portfolio_name}' from trading node.")
        else:
            print(f"Syncing portfolio '{portfolio_name}' from trading node.")

        # Get the class paths of all strategies currently running on the node
        running_strategy_paths = {
            f"{s.__class__.__module__}.{s.__class__.__name__}" for s in node.strategies
        }

        # Deactivate any instances in the DB that are no longer running on the node
        deactivated_count, _ = portfolio.strategy_instances.exclude(
            strategy_model__class_path__in=running_strategy_paths
        ).update(is_active=False)

        if deactivated_count > 0:
            print(f"Deactivated {deactivated_count} strategy instance(s) no longer on the node.")

        # Add or update strategy instances from the node
        for strategy in node.strategies:
            class_path = f"{strategy.__class__.__module__}.{strategy.__class__.__name__}"
            strategy_model = Strategy.objects.get(class_path=class_path)
            raw_id = str(strategy.instrument_id)
            parts = raw_id.split(".")
            symbol = parts[0]
            venue = parts[1] if len(parts) > 1 else "SMART"
            instrument, _ = Instrument.objects.get_or_create(
                symbol=symbol,
                venue=venue,
                defaults={'is_active': True}
            )

            StrategyInstance.objects.update_or_create(
                portfolio=portfolio,
                strategy_model=strategy_model,
                instrument=instrument,
                defaults={'params': strategy.config, 'is_active': True}
            )
        print(f"Synced {len(node.strategies)} strategy instance(s).")
        return portfolio


class StrategyInstance(models.Model):
    """
    A specific, parameterized instance of a strategy for a given instrument,
    assigned to a portfolio.
    """
    portfolio = models.ForeignKey(Portfolio, on_delete=models.CASCADE, related_name='strategy_instances')
    strategy_model = models.ForeignKey(Strategy, on_delete=models.CASCADE, related_name='instances')
    instrument = models.ForeignKey(
        'Instrument',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='strategy_instances',
        help_text=_("The instrument this strategy instance trades.")
    )
    description = models.TextField(blank=True, help_text=_("Description or trading rationale for this instance."))
    params = models.JSONField(default=dict, blank=True, help_text="JSON object of strategy-specific parameters.")
    is_active = models.BooleanField(default=True)

    @property
    def instrument_id(self) -> str:
        return self.instrument.instrument_id_str if self.instrument else ""

    def __str__(self):
        return f"{self.strategy_model.name} on {self.instrument} in {self.portfolio.name}"


# =============================================================================
# ALPHA SCANNER, SIGNAL, AND RECOMMENDATION MODELS
# =============================================================================

class Scanner(models.Model):
    """
    A configurable scanner to find trading opportunities (alpha).
    This is a template for a type of scan (e.g., "Volume Spike Scanner").
    """
    name = models.CharField(max_length=100, unique=True)
    scanner_class_path = models.CharField(
        max_length=255,
        unique=True,
        help_text="Full Python path to the scanner class (e.g., 'argo.scanners.volatility.VolatilityScanner')."
    )
    description = models.TextField(blank=True)
    # Default parameters that instances of this scanner might use
    default_params = models.JSONField(default=dict, blank=True)

    def __str__(self):
        return self.name


class Signal(models.Model):
    """
    Represents a potential trading opportunity identified by a Scanner.
    """
    class SignalType(models.TextChoices):
        BULLISH = 'BULLISH', _('Bullish')
        BEARISH = 'BEARISH', _('Bearish')
        NEUTRAL = 'NEUTRAL', _('Neutral')

    class SignalStatus(models.TextChoices):
        NEW = 'NEW', _('New')
        VIEWED = 'VIEWED', _('Viewed')
        ACTIONED = 'ACTIONED', _('Actioned')
        DISMISSED = 'DISMISSED', _('Dismissed')

    scanner = models.ForeignKey(Scanner, on_delete=models.CASCADE, related_name='signals')
    instrument_id = models.CharField(max_length=100)
    signal_type = models.CharField(max_length=10, choices=SignalType.choices)
    status = models.CharField(max_length=10, choices=SignalStatus.choices, default=SignalStatus.NEW)
    confidence = models.FloatField(help_text="Confidence score from 0.0 to 1.0.", null=True, blank=True)
    details = models.JSONField(default=dict, blank=True, help_text="Scanner-specific data, e.g., indicator values.")
    generated_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.signal_type} signal for {self.instrument_id} from {self.scanner.name}"

    class Meta:
        ordering = ['-generated_at']


class Recommendation(models.Model):
    """
    A concrete recommendation to act on a Signal, suggesting a specific
    strategy and its configuration.
    """
    class RecommendationStatus(models.TextChoices):
        PENDING = 'PENDING', _('Pending')
        ACCEPTED = 'ACCEPTED', _('Accepted')
        REJECTED = 'REJECTED', _('Rejected')

    signal = models.OneToOneField(Signal, on_delete=models.CASCADE, related_name='recommendation')
    recommended_strategy = models.ForeignKey(Strategy, on_delete=models.CASCADE)
    recommended_params = models.JSONField(
        default=dict,
        help_text="Suggested parameters for the strategy instance (e.g., stop loss, take profit)."
    )
    justification = models.TextField(blank=True, help_text="Why this strategy is recommended for this signal.")
    status = models.CharField(max_length=10, choices=RecommendationStatus.choices, default=RecommendationStatus.PENDING)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Recommend {self.recommended_strategy.name} for {self.signal.instrument_id}"

    def accept(self, portfolio: Portfolio):
        """Creates and activates a StrategyInstance based on this recommendation."""
        parts = self.signal.instrument_id.split(".")
        symbol = parts[0]
        venue = parts[1] if len(parts) > 1 else "SMART"
        instrument, _ = Instrument.objects.get_or_create(
            symbol=symbol,
            venue=venue,
            defaults={'is_active': True}
        )
        instance, created = StrategyInstance.objects.update_or_create(
            portfolio=portfolio,
            strategy_model=self.recommended_strategy,
            instrument=instrument,
            defaults={
                'params': self.recommended_params,
                'is_active': True,
            }
        )
        self.status = self.RecommendationStatus.ACCEPTED
        self.save()
        return instance


# =============================================================================
# INSTRUMENT AND BROKER CONTRACT MODELS
# =============================================================================

class AssetClass(models.TextChoices):
    EQUITY = 'EQUITY', _('Equity')
    FUTURE = 'FUTURE', _('Future')
    OPTION = 'OPTION', _('Option')
    FX = 'FX', _('Forex')
    COMMODITY = 'COMMODITY', _('Commodity')
    CRYPTO = 'CRYPTO', _('Crypto')
    INDEX = 'INDEX', _('Index')


class OptionRight(models.TextChoices):
    CALL = 'CALL', _('Call')
    PUT = 'PUT', _('Put')


class InstrumentGroup(AfterSaveActionMixin, models.Model, GetContentsMixin, TaskHolder):
    """
    A collection of instruments grouped for trading universes, scans, or execution.
    """
    TASK_TEXT_GENERATE = getattr(settings, 'TASK_TYPE_GENERATE_TEXT', 'generate_text')

    PRESET_CREATE_SYMBOLS = "create_symbols"
    PRESET_SYNC_SYMBOLS = "sync_symbols"

    ACTION_CREATE_SYMBOLS = f"{TASK_TEXT_GENERATE}-preset-{PRESET_CREATE_SYMBOLS}-target-symbols-schema-outwithmsg"
    ACTION_SYNC_SYMBOLS = f"{TASK_TEXT_GENERATE}-preset-{PRESET_SYNC_SYMBOLS}-target-symbols-schema-symbols"

    ACTION_CHOICES = (
        (ACTION_CREATE_SYMBOLS, _("Create symbols from description")),
        (ACTION_SYNC_SYMBOLS, _("Sync symbols")),
    ) + getattr(settings, 'COMMON_TEXT_ACTION_CHOICES', ())

    AGENT_PRESETS = (
        (PRESET_CREATE_SYMBOLS, _("Create symbols")),
        (PRESET_SYNC_SYMBOLS, _("Sync symbols")),
    ) + getattr(settings, 'COMMON_TEXT_AGENT_PRESETS', ())

    name = models.CharField(max_length=100, unique=True)
    code = models.CharField(max_length=50, unique=True, help_text=_("Short identifier for the group (e.g., 'US_TECH', 'FX_MAJORS')."))
    description = models.TextField(blank=True)
    asset_class = models.CharField(max_length=16, choices=AssetClass.choices, default=AssetClass.EQUITY)
    venue = models.CharField(max_length=32, default='SMART', help_text=_("Default venue/exchange for instruments in this group."))
    currency = models.CharField(max_length=8, default='USD')
    symbols = models.TextField(blank=True, help_text=_("Comma, space, or newline-separated symbols to populate (e.g., 'AAPL, MSFT, NVDA')."))
    is_active = models.BooleanField(default=True)

    action = models.SlugField(_("action"), max_length=1024, choices=ACTION_CHOICES, null=True, blank=True)
    history = HistoricalRecords()

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _('Instrument Group')
        verbose_name_plural = _('Instrument Groups')
        ordering = ['name']

    def __str__(self):
        return f"{self.name} ({self.code})"


    def get_contents(self, generate_self=True, preset=None):
        parts = []
        if preset in [self.PRESET_CREATE_SYMBOLS]:
            if self.description:
                parts.append(f"Description: {self.description}")
            if self.name:
                parts.append(f"Group Name: {self.name}")
        elif preset in [self.PRESET_SYNC_SYMBOLS]:
            parts.append(f"<Symbols>{self.symbols}<Symbols>")
        else:
            parts = super().get_contents(generate_self=generate_self, preset=preset)
        return parts

    def get_symbols_as_json(self) -> str:
        from .schemas import SymbolsSchema
        return SymbolsSchema.from_group(self).model_dump_json(indent=2)


    def get_codes(self) -> list[str]:
        """Extracts and deduplicates clean symbol codes from the symbols definition."""
        if not self.symbols:
            return []
        raw_codes = re.split(r'[\s,;]+', self.symbols.strip())
        return sorted({code.strip().upper() for code in raw_codes if code.strip()})

    def create_instruments(self) -> tuple[int, int]:
        """Creates Instrument and default IBContract objects for each code in this group."""
        codes = self.get_codes()
        created_count = 0
        sec_type_map = {
            AssetClass.EQUITY: 'STK',
            AssetClass.FUTURE: 'FUT',
            AssetClass.OPTION: 'OPT',
            AssetClass.FX: 'CASH',
            AssetClass.CRYPTO: 'CRYPTO',
            AssetClass.INDEX: 'IND',
            AssetClass.COMMODITY: 'CMDTY',
        }
        default_sec_type = sec_type_map.get(self.asset_class, 'STK')

        for code in codes:
            instrument, created = Instrument.objects.get_or_create(
                symbol=code,
                venue=self.venue,
                asset_class=self.asset_class,
                defaults={
                    'currency': self.currency,
                    'is_active': True,
                },
            )
            instrument.groups.add(self)
            IBContract.objects.get_or_create(
                instrument=instrument,
                defaults={
                    'sec_type': default_sec_type,
                    'exchange': self.venue,
                },
            )
            if created:
                created_count += 1

        return created_count, len(codes)

    def populate_symbols_from_ib(self, query: str, append: bool = False) -> list[str]:
        """Discovers symbols matching query via IB and updates group symbols."""
        from argo.instruments.search import InteractiveBrokersSearchService
        return InteractiveBrokersSearchService().populate_group(self, query=query, append=append)




class Instrument(models.Model):
    """
    Generalized financial instrument metadata for backtesting and execution.
    """
    groups = models.ManyToManyField(InstrumentGroup, related_name='instruments', blank=True)
    symbol = models.CharField(max_length=64, db_index=True)
    venue = models.CharField(max_length=32, db_index=True)
    asset_class = models.CharField(max_length=16, choices=AssetClass.choices, default=AssetClass.EQUITY)
    currency = models.CharField(max_length=8, default='USD')
    quote_currency = models.CharField(max_length=8, null=True, blank=True)

    price_precision = models.PositiveSmallIntegerField(default=2)
    size_precision = models.PositiveSmallIntegerField(default=0)
    price_increment = models.DecimalField(max_digits=12, decimal_places=6, default=0.01)
    size_increment = models.DecimalField(max_digits=12, decimal_places=6, default=1.0)
    lot_size = models.DecimalField(max_digits=12, decimal_places=4, default=1.0)
    multiplier = models.DecimalField(max_digits=12, decimal_places=4, default=1.0)

    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('symbol', 'venue', 'asset_class')
        ordering = ['symbol', 'venue']

    def __str__(self):
        return f"{self.symbol}.{self.venue} ({self.asset_class})"

    @property
    def instrument_id_str(self) -> str:
        return f"{self.symbol}.{self.venue}"


class IBContract(models.Model):
    """
    Interactive Brokers contract specification linked 1:1 with an Instrument.
    """
    instrument = models.OneToOneField(Instrument, on_delete=models.CASCADE, related_name='ib_contract')
    con_id = models.PositiveBigIntegerField(unique=True, null=True, blank=True)
    sec_type = models.CharField(max_length=16, default='STK', help_text="STK, FUT, OPT, CASH, IND, CRYPTO, CFD")
    exchange = models.CharField(max_length=32, default='SMART')
    primary_exchange = models.CharField(max_length=32, blank=True)
    local_symbol = models.CharField(max_length=64, blank=True)
    trading_class = models.CharField(max_length=32, blank=True)

    expiration = models.DateField(null=True, blank=True)
    strike = models.DecimalField(max_digits=12, decimal_places=4, null=True, blank=True)
    option_right = models.CharField(max_length=4, choices=OptionRight.choices, blank=True)
    include_expired = models.BooleanField(default=False)

    class Meta:
        verbose_name = _('IB Contract')
        verbose_name_plural = _('IB Contracts')

    def __str__(self):
        return f"IB:{self.sec_type} {self.instrument.symbol} @ {self.exchange} (ID: {self.con_id or 'N/A'})"