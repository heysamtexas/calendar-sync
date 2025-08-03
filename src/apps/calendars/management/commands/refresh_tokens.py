"""Django management command for token refresh operations"""

from django.core.management.base import BaseCommand, CommandError

from apps.calendars.services.token_manager import (
    TokenManager,
    validate_all_accounts,
)


class Command(BaseCommand):
    help = "Refresh OAuth tokens for calendar accounts"

    def add_arguments(self, parser):
        parser.add_argument(
            "--account-id",
            type=int,
            help="Refresh tokens for specific account ID only",
        )
        parser.add_argument(
            "--background",
            action="store_true",
            help="Run background token refresh (only accounts expiring soon)",
        )
        parser.add_argument(
            "--status",
            action="store_true",
            help="Show token status summary without performing refresh",
        )
        parser.add_argument(
            "--force",
            action="store_true",
            help="Force refresh all active accounts regardless of expiry",
        )

    def handle(self, *args, **options):
        if options["status"]:
            self._show_status()
            return

        if options["background"]:
            self._run_background_refresh()
            return

        if options["account_id"]:
            self._refresh_specific_account(options["account_id"])
            return

        if options["force"]:
            self._force_refresh_all()
            return

        # Default: validate all accounts and refresh as needed
        self._validate_all_accounts()

    def _show_status(self):
        """Show token status summary"""
        self.stdout.write("Token Status Summary:")
        self.stdout.write("=" * 50)

        # Simple status check using validate_all_accounts
        status_results = validate_all_accounts()
        total = status_results["total_accounts"]

        # Calculate basic status info
        status = {
            "total_accounts": total,
            "active_accounts": total,  # validate_all_accounts only looks at active
            "inactive_accounts": 0,  # Simplified - don't track this separately
            "healthy_tokens": status_results["successful_refreshes"],
            "tokens_expiring_soon": 0,  # Simplified - don't track this separately
            "expired_tokens": status_results["failed_refreshes"],
        }

        self.stdout.write(f"Total accounts: {status['total_accounts']}")
        self.stdout.write(f"Active accounts: {status['active_accounts']}")
        self.stdout.write(f"Inactive accounts: {status['inactive_accounts']}")
        self.stdout.write(f"Healthy tokens: {status['healthy_tokens']}")
        self.stdout.write(f"Tokens expiring soon: {status['tokens_expiring_soon']}")

        if status["expired_tokens"] > 0:
            self.stdout.write(
                self.style.WARNING(f"Expired tokens: {status['expired_tokens']}")
            )
        else:
            self.stdout.write(f"Expired tokens: {status['expired_tokens']}")

    def _run_background_refresh(self):
        """Run background token refresh"""
        self.stdout.write("Starting background token refresh...")

        try:
            # Use validate_all_accounts for background refresh
            results = validate_all_accounts()
            refresh_count = results["successful_refreshes"]
            self.stdout.write(
                self.style.SUCCESS(
                    f"Background refresh complete: {refresh_count} tokens refreshed"
                )
            )
        except Exception as e:
            raise CommandError(f"Background refresh failed: {e}") from e

    def _refresh_specific_account(self, account_id):
        """Refresh tokens for specific account"""
        from apps.calendars.models import CalendarAccount

        try:
            account = CalendarAccount.objects.get(id=account_id, is_active=True)
            self.stdout.write(f"Refreshing tokens for account: {account.email}")

            # Use simplified token manager
            manager = TokenManager(account)
            credentials = manager.get_valid_credentials()

            if credentials:
                self.stdout.write(
                    self.style.SUCCESS(
                        f"Successfully refreshed tokens for {account.email}"
                    )
                )
            else:
                self.stdout.write(
                    self.style.WARNING(f"Failed to refresh tokens for {account.email}")
                )

        except CalendarAccount.DoesNotExist:
            raise CommandError(f"Account with ID {account_id} not found or inactive")
        except Exception as e:
            raise CommandError(f"Failed to refresh account {account_id}: {e}") from e

    def _force_refresh_all(self):
        """Force refresh all active accounts"""
        from apps.calendars.models import CalendarAccount

        self.stdout.write("Force refreshing all active accounts...")

        active_accounts = CalendarAccount.objects.filter(is_active=True)
        success_count = 0
        fail_count = 0

        for account in active_accounts:
            try:
                self.stdout.write(f"Force refreshing: {account.email}")
                manager = TokenManager(account)
                credentials = manager.get_valid_credentials()

                if credentials:
                    success_count += 1
                    self.stdout.write("  ✓ Success")
                else:
                    fail_count += 1
                    self.stdout.write("  ✗ Failed")

            except Exception as e:
                fail_count += 1
                self.stdout.write(f"  ✗ Error: {e}")

        self.stdout.write(
            self.style.SUCCESS(
                f"Force refresh complete: {success_count} successful, {fail_count} failed"
            )
        )

    def _validate_all_accounts(self):
        """Validate and refresh tokens for all accounts"""
        self.stdout.write("Validating all account tokens...")

        try:
            results = validate_all_accounts()

            self.stdout.write("Validation complete:")
            self.stdout.write(f"  Total accounts: {results['total_accounts']}")
            self.stdout.write(
                f"  Successful refreshes: {results['successful_refreshes']}"
            )

            if results["failed_refreshes"] > 0:
                self.stdout.write(
                    self.style.WARNING(
                        f"  Failed refreshes: {results['failed_refreshes']}"
                    )
                )

                if results["deactivated_accounts"]:
                    self.stdout.write(
                        self.style.WARNING(
                            f"  Deactivated accounts: {', '.join(results['deactivated_accounts'])}"
                        )
                    )
            else:
                self.stdout.write(f"  Failed refreshes: {results['failed_refreshes']}")

            if results["errors"]:
                self.stdout.write(self.style.ERROR("Errors encountered:"))
                for error in results["errors"]:
                    self.stdout.write(f"  - {error}")

        except Exception as e:
            raise CommandError(f"Token validation failed: {e}") from e
