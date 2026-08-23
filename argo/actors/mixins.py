from argo.models import Account


class AccountSyncMixin:
    """
    Mixin for NautilusTrader Strategy classes to automatically synchronize
    Nautilus account state and cache to Django Account models.
    """

    def sync_accounts(self) -> list[Account]:
        """
        Synchronizes all accounts currently in the strategy cache to Django models.
        """
        synced = []
        accounts = self.cache.accounts() if hasattr(self, "cache") else []
        for account in accounts:
            try:
                acc_obj = Account.sync_from_nautilus(account)
                synced.append(acc_obj)
                if hasattr(self, "log"):
                    self.log.info(
                        f"Synchronized account {acc_obj.account_id} to database "
                        f"(balance: {acc_obj.balance_total} {acc_obj.base_currency})"
                    )
            except Exception as e:
                if hasattr(self, "log"):
                    self.log.error(f"Failed to synchronize account {account}: {e}")
        return synced

    def on_account_state(self, event) -> None:
        """
        Handles incoming AccountState events and syncs the updated state to the DB.
        """
        try:
            acc_obj = Account.sync_from_nautilus(event)
            if hasattr(self, "log"):
                self.log.info(f"Account state updated for {acc_obj.account_id}")
        except Exception as e:
            if hasattr(self, "log"):
                self.log.error(f"Error syncing account state event: {e}")

        if hasattr(super(), "on_account_state"):
            super().on_account_state(event)
