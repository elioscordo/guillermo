from nautilus_trader.common.actor import Actor
from nautilus_trader.core.message import Event


class EventLoggerActor(Actor):
    """
    A simple observer actor that subscribes to all global events
    and logs/prints them to standard output.
    """

    def on_start(self) -> None:
        self.log.info("EventLoggerActor started. Subscribing to all events...")

        # Subscribe to all execution events (orders, fills, cancels)
        self.msgbus.subscribe(topic="events.execution.*", handler=self.handle_event)

        # Subscribe to all portfolio events (positions open, change, close)
        self.msgbus.subscribe(topic="events.portfolio.*", handler=self.handle_event)

        # Subscribe to all account/balance events
        self.msgbus.subscribe(topic="events.account.*", handler=self.handle_event)

        # Optional: subscribe to all data events (ticks, bars, book updates)
        # Warning: very verbose if subscribing to live tick feeds!
        # self.msgbus.subscribe(topic="data.*", handler=self.handle_event)

    def handle_event(self, event: Event) -> None:
        """Catch-all event handler for printing."""
        event_name = type(event).__name__
        timestamp = getattr(event, "ts_event", "N/A")

        print(f"[{timestamp}] EVENT: {event_name}")
        print(f"  -> Details: {event}")
        print("-" * 50)

    def on_stop(self) -> None:
        self.log.info("EventLoggerActor stopped.")