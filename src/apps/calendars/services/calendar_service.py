"""Calendar business logic service"""

from django.db import models, transaction

from ..models import Calendar, CalendarAccount
from .base import (
    BaseService,
    BusinessLogicError,
    ExternalServiceError,
    ResourceNotFoundError,
)


class CalendarService(BaseService):
    """Service for calendar business operations"""

    def set_calendar_sync_status(self, calendar_id, enabled):
        """Set calendar sync status with immediate response (Guilfoyle's locked state pattern)"""
        try:
            with transaction.atomic():
                # Use select_for_update to prevent race conditions (Guilfoyle's requirement)
                calendar = Calendar.objects.select_for_update().select_related("calendar_account").get(
                    id=calendar_id
                )

                # Validate user permission
                self._validate_user_permission(calendar, "calendar_account__user")

                # CRITICAL: Prevent re-enabling during cleanup (Guilfoyle's protection)
                if enabled and calendar.cleanup_pending:
                    raise BusinessLogicError(
                        "Cannot enable sync while cleanup is in progress. "
                        "Please wait for cleanup to complete (~1-2 minutes)."
                    )

                old_status = calendar.sync_enabled
                
                # If no change, return early
                if old_status == enabled:
                    return calendar
                # Set new sync status
                calendar.sync_enabled = enabled
                
                # If disabling sync, mark for async cleanup instead of blocking
                if old_status and not enabled:
                    from django.utils import timezone
                    calendar.cleanup_pending = True
                    calendar.cleanup_requested_at = timezone.now()
                    calendar.save(update_fields=["sync_enabled", "cleanup_pending", "cleanup_requested_at"])
                    
                    self.logger.debug(f"Marked {calendar.name} for async cleanup")
                else:
                    calendar.save(update_fields=["sync_enabled"])

                # If enabling sync, validate tokens and trigger initial sync
                if not old_status and enabled:
                    sync_result = self._enable_calendar_sync_with_validation(calendar)
                    if not sync_result["success"]:
                        # Revert changes on failure
                        calendar.sync_enabled = False
                        calendar.save(update_fields=["sync_enabled"])
                        raise BusinessLogicError(sync_result["error"])

            # Log operation
            self._log_operation(
                "calendar_sync_status_change",
                calendar_id=calendar.id,
                calendar_name=calendar.name,
                old_status=old_status,
                new_status=calendar.sync_enabled,
                cleanup_scheduled=old_status and not enabled,
                token_refresh_attempted=not old_status and enabled,
            )

            return calendar

        except Calendar.DoesNotExist:
            raise ResourceNotFoundError(f"Calendar {calendar_id} not found")

    def toggle_calendar_sync(self, calendar_id):
        """Toggle sync status for a calendar (wrapper for backward compatibility)"""
        calendar = Calendar.objects.select_related("calendar_account").get(
            id=calendar_id
        )
        return self.set_calendar_sync_status(calendar_id, not calendar.sync_enabled)

    def bulk_toggle_calendars(self, calendar_ids, enable=True):
        """Toggle multiple calendars efficiently"""
        calendars = Calendar.objects.filter(
            id__in=calendar_ids, calendar_account__user=self.user
        ).select_related("calendar_account")

        if not calendars.exists():
            raise ResourceNotFoundError("No accessible calendars found")

        with transaction.atomic():
            updated_calendars = []
            newly_enabled_calendars = []
            newly_disabled_calendars = []
            
            for calendar in calendars:
                if calendar.sync_enabled != enable:
                    # CRITICAL: Prevent bulk re-enabling during cleanup (Guilfoyle's protection)
                    if enable and calendar.cleanup_pending:
                        self.logger.warning(
                            f"Skipping {calendar.name} - cleanup in progress"
                        )
                        continue
                    
                    old_status = calendar.sync_enabled
                    calendar.sync_enabled = enable
                    
                    # If disabling sync, mark for async cleanup instead of blocking
                    if old_status and not enable:
                        from django.utils import timezone
                        calendar.cleanup_pending = True
                        calendar.cleanup_requested_at = timezone.now()
                        calendar.save(update_fields=["sync_enabled", "cleanup_pending", "cleanup_requested_at"])
                        newly_disabled_calendars.append(calendar)
                    else:
                        calendar.save(update_fields=["sync_enabled"])
                    
                    updated_calendars.append(calendar)
                    
                    # Track calendars that were just enabled
                    if not old_status and enable:
                        newly_enabled_calendars.append(calendar)

            # Trigger initial sync for newly enabled calendars with validation
            failed_calendars = []
            for calendar in newly_enabled_calendars:
                sync_result = self._enable_calendar_sync_with_validation(calendar)
                if not sync_result["success"]:
                    # Revert this calendar's sync status
                    calendar.sync_enabled = False
                    calendar.save(update_fields=["sync_enabled"])
                    failed_calendars.append({
                        "calendar": calendar,
                        "error": sync_result["error"],
                        "error_type": sync_result["error_type"]
                    })
                    self.logger.warning(
                        f"Failed to enable sync for {calendar.name}: {sync_result['error']}"
                    )
            
            # Log async cleanup scheduling for disabled calendars
            if newly_disabled_calendars:
                self.logger.debug(f"Marked {len(newly_disabled_calendars)} calendars for async cleanup")

            self._log_operation(
                "bulk_calendar_status_change",
                calendar_count=len(updated_calendars),
                enabled=enable,
                initial_syncs_triggered=len(newly_enabled_calendars) - len(failed_calendars),
                failed_syncs=len(failed_calendars),
                async_cleanups_scheduled=len(newly_disabled_calendars),
            )

            # If there were failures, include them in the result
            result = {
                "updated_calendars": updated_calendars,
                "failed_calendars": failed_calendars
            }
            
            return result if failed_calendars else updated_calendars

    def check_for_stuck_cleanup(self):
        """Check for and recover calendars stuck in cleanup state (Guilfoyle's requirement)"""
        from datetime import timedelta
        from django.utils import timezone
        
        # Find calendars stuck in cleanup for more than 10 minutes
        stuck_threshold = timezone.now() - timedelta(minutes=10)
        stuck_calendars = Calendar.objects.filter(
            cleanup_pending=True,
            cleanup_requested_at__lt=stuck_threshold
        ).select_related('calendar_account')
        
        recovered_count = 0
        for calendar in stuck_calendars:
            try:
                self.logger.error(
                    f"Found stuck cleanup for calendar {calendar.id} ({calendar.name}). "
                    f"Last updated: {calendar.updated_at}"
                )
                
                # Clear the stuck state
                calendar.cleanup_pending = False
                calendar.save(update_fields=['cleanup_pending'])
                recovered_count += 1
                
                self.logger.info(f"Recovered stuck calendar {calendar.name}")
                
            except Exception as e:
                self.logger.critical(
                    f"Failed to recover stuck calendar {calendar.id}: {e}"
                )
        
        if recovered_count > 0:
            self._log_operation(
                "stuck_cleanup_recovery",
                recovered_calendars=recovered_count,
                total_stuck_found=stuck_calendars.count()
            )
        
        return recovered_count

    def get_user_calendar_stats(self):
        """Get calendar statistics for user"""
        stats = CalendarAccount.objects.filter(user=self.user).aggregate(
            total_accounts=models.Count("id"),
            active_accounts=models.Count("id", filter=models.Q(is_active=True)),
            total_calendars=models.Count("calendars"),
            sync_enabled_calendars=models.Count(
                "calendars", filter=models.Q(calendars__sync_enabled=True)
            ),
        )

        return stats

    def refresh_calendar_list(self, account_id):
        """Refresh calendar list for an account"""
        try:
            account = CalendarAccount.objects.get(id=account_id, user=self.user)

            if not account.is_active:
                raise BusinessLogicError(
                    "Cannot refresh calendars for inactive account"
                )

            # Use existing GoogleCalendarClient
            from .google_calendar_client import GoogleCalendarClient

            client = GoogleCalendarClient(account)

            try:
                calendars_data = client.list_calendars()
            except Exception as e:
                raise ExternalServiceError(f"Failed to fetch calendars: {e!s}")

            with transaction.atomic():
                calendars_created = 0
                calendars_updated = 0

                for cal_item in calendars_data:
                    calendar, created = Calendar.objects.update_or_create(
                        calendar_account=account,
                        google_calendar_id=cal_item["id"],
                        defaults={
                            "name": cal_item.get("summary", "Unnamed Calendar"),
                            "is_primary": cal_item.get("primary", False),
                            "description": cal_item.get("description", ""),
                            "color": cal_item.get("backgroundColor", ""),
                        },
                    )

                    if created:
                        calendar.sync_enabled = False  # Safe default
                        calendar.save(update_fields=["sync_enabled"])
                        calendars_created += 1
                    else:
                        calendars_updated += 1

                self._log_operation(
                    "calendar_refresh",
                    account_id=account.id,
                    calendars_found=len(calendars_data),
                    calendars_created=calendars_created,
                    calendars_updated=calendars_updated,
                )

                return {
                    "calendars_found": len(calendars_data),
                    "calendars_created": calendars_created,
                    "calendars_updated": calendars_updated,
                }

        except CalendarAccount.DoesNotExist:
            raise ResourceNotFoundError(f"Account {account_id} not found")
        except (BusinessLogicError, ExternalServiceError):
            raise
        except Exception as e:
            self._handle_error(e, "calendar_refresh", account_id=account_id)
            raise ExternalServiceError(f"Calendar refresh failed: {e!s}")

    def get_calendar_with_stats(self, calendar_id):
        """Get calendar with event statistics"""
        try:
            calendar = (
                Calendar.objects.select_related("calendar_account")
                .annotate(
                    event_count=models.Count("events"),
                    busy_block_count=models.Count(
                        "events", filter=models.Q(events__is_busy_block=True)
                    ),
                )
                .get(id=calendar_id)
            )

            # Validate user permission
            self._validate_user_permission(calendar, "calendar_account__user")

            return calendar

        except Calendar.DoesNotExist:
            raise ResourceNotFoundError(f"Calendar {calendar_id} not found")

    def get_user_calendars_optimized(self):
        """Get all user calendars with optimized queries"""
        return (
            Calendar.objects.filter(calendar_account__user=self.user)
            .select_related("calendar_account")
            .annotate(
                event_count=models.Count("events"),
                busy_block_count=models.Count(
                    "events", filter=models.Q(events__is_busy_block=True)
                ),
            )
            .order_by("calendar_account__email", "name")
        )

    def validate_calendar_sync_requirements(self, calendar, attempt_token_refresh=False):
        """Validate if calendar can be synced, optionally attempting token refresh"""
        if not calendar.calendar_account.is_active:
            return False, "Account is inactive"

        if calendar.calendar_account.is_token_expired:
            if attempt_token_refresh:
                try:
                    from .token_manager import TokenManager
                    token_manager = TokenManager(calendar.calendar_account)
                    credentials = token_manager.get_valid_credentials()
                    
                    if credentials:
                        # Refresh the calendar account from DB to get updated token info
                        calendar.calendar_account.refresh_from_db()
                        self.logger.info(f"Successfully refreshed token for {calendar.name}")
                    else:
                        return False, "Token has expired and refresh failed"
                        
                except Exception as e:
                    self.logger.error(f"Token refresh failed for {calendar.name}: {e}")
                    return False, "Token has expired and refresh failed"
            else:
                return False, "Token has expired"

        if not calendar.sync_enabled:
            return False, "Sync is disabled for this calendar"

        try:
            if not calendar.calendar_account.user.profile.sync_enabled:
                return False, "Global sync is disabled for user"
        except AttributeError:
            return False, "User profile not configured"

        return True, "Calendar is ready for sync"

    def _trigger_initial_sync(self, calendar):
        """Trigger initial sync when calendar is enabled"""
        try:
            # Validate calendar can be synced
            can_sync, reason = calendar.can_sync()
            if not can_sync:
                self.logger.warning(
                    f"Cannot trigger initial sync for {calendar.name}: {reason}"
                )
                return

            # Import sync engine
            from .uuid_sync_engine import sync_calendar_yolo

            # Trigger sync in background-friendly way
            self.logger.info(f"Triggering initial sync for {calendar.name}")
            
            try:
                # Regular outbound sync
                result = sync_calendar_yolo(calendar)
                
                # PLUS: Inbound sync - create busy blocks from existing events in other calendars
                inbound_repairs = self._create_inbound_busy_blocks(calendar)
                
                self._log_operation(
                    "initial_sync_triggered",
                    calendar_id=calendar.id,
                    calendar_name=calendar.name,
                    result=result,
                    inbound_repairs=inbound_repairs,
                )
                self.logger.info(
                    f"Initial sync completed for {calendar.name}: "
                    f"{result.get('user_events_found', 0)} events found, "
                    f"{result.get('busy_blocks_created', 0)} busy blocks created, "
                    f"{inbound_repairs} inbound busy blocks created"
                )
            except Exception as e:
                self.logger.error(f"Initial sync failed for {calendar.name}: {e}")
                self._log_operation(
                    "initial_sync_failed",
                    calendar_id=calendar.id,
                    calendar_name=calendar.name,
                    error=str(e),
                )

        except Exception as e:
            self.logger.error(f"Failed to trigger initial sync for {calendar.name}: {e}")

    def _create_inbound_busy_blocks(self, target_calendar):
        """Create busy blocks from existing events in other calendars (inbound sync)"""
        try:
            # Get other calendars for same user
            other_calendars = Calendar.objects.filter(
                calendar_account__user=target_calendar.calendar_account.user,
                sync_enabled=True,
                calendar_account__is_active=True,
            ).exclude(id=target_calendar.id)

            repairs_made = 0
            
            for source_calendar in other_calendars:
                # Get legitimate user events from source calendar
                user_events = source_calendar.event_states.filter(
                    is_busy_block=False,
                    status__in=["SYNCED", "PENDING"]  # Not deleted events
                )
                
                for source_event in user_events:
                    # Check if busy block already exists
                    from apps.calendars.models import EventState
                    existing_busy_block = EventState.objects.filter(
                        calendar=target_calendar,
                        source_uuid=source_event.uuid,
                        is_busy_block=True,
                    ).exists()
                    
                    if not existing_busy_block:
                        try:
                            # Create the missing busy block
                            self._create_busy_block_from_event(source_event, target_calendar)
                            repairs_made += 1
                            
                            self.logger.info(
                                f"Created inbound busy block in {target_calendar.name} "
                                f"from {source_event.title[:30]}... in {source_calendar.name}"
                            )
                        except Exception as e:
                            self.logger.error(
                                f"Failed to create inbound busy block: {e}"
                            )

            return repairs_made

        except Exception as e:
            self.logger.error(f"Failed to create inbound busy blocks: {e}")
            return 0

    def _create_busy_block_from_event(self, source_event, target_calendar):
        """Create a single busy block from a source event"""
        from apps.calendars.models import EventState
        from apps.calendars.services.google_calendar_client import GoogleCalendarClient
        
        # Create EventState first (database-first)
        busy_block_state = EventState.create_busy_block(
            target_calendar=target_calendar,
            source_uuid=source_event.uuid,
            title=source_event.title or "Event",
        )
        
        # Create in Google Calendar
        client = GoogleCalendarClient(target_calendar.calendar_account)
        
        # Clean title to prevent "Busy - Busy -" prefixes
        clean_title = source_event.title or "Event"
        if clean_title.startswith("Busy - "):
            clean_title = clean_title[7:]
        
        event_data = {
            "summary": f"Busy - {clean_title}",
            "description": f"Busy block from {source_event.calendar.name}",
            "start": self._format_event_datetime(source_event.start_time),
            "end": self._format_event_datetime(source_event.end_time),
            "transparency": "opaque",
            "visibility": "private",
        }
        
        created_event = client.create_event_with_uuid_correlation(
            calendar_id=target_calendar.google_calendar_id,
            event_data=event_data,
            correlation_uuid=str(busy_block_state.uuid),
            skip_title_embedding=True,
        )
        
        if created_event:
            busy_block_state.mark_synced(created_event["id"])
            return busy_block_state
        else:
            busy_block_state.mark_deleted()
            raise Exception("Failed to create busy block in Google Calendar")

    def _format_event_datetime(self, dt):
        """Format datetime for Google Calendar API"""
        if not dt:
            from django.utils import timezone
            dt = timezone.now()
        
        return {
            "dateTime": dt.isoformat(),
            "timeZone": "UTC",
        }

    def _execute_gone_gone_cleanup(self, calendar):
        """Execute 'Gone Gone' cleanup when calendar sync is disabled"""
        try:
            self.logger.debug(f"Starting 'Gone Gone' cleanup for {calendar.name}")
            
            # Step 1: Collect data before cleanup
            cleanup_stats = self._analyze_cleanup_scope(calendar)
            
            # Step 2: Clean up outbound busy blocks (this calendar's events in other calendars)
            outbound_cleaned = self._cleanup_outbound_busy_blocks(calendar)
            
            # Step 3: Clean up local events and busy blocks
            local_cleaned = self._cleanup_calendar_events(calendar)
            
            # Log results - single summary log (Guilfoyle's reduced verbosity)
            self._log_operation(
                "gone_gone_cleanup",
                calendar_id=calendar.id,
                calendar_name=calendar.name,
                local_events_cleaned=local_cleaned,
                outbound_busy_blocks_cleaned=outbound_cleaned,
                **cleanup_stats,
            )
            
            self.logger.info(
                f"Gone Gone cleanup completed: calendar={calendar.name}, "
                f"local_events={local_cleaned}, outbound_blocks={outbound_cleaned}"
            )

        except Exception as e:
            self.logger.error(f"Gone Gone cleanup failed for {calendar.name}: {e}")
            raise

    def _analyze_cleanup_scope(self, calendar):
        """Analyze what will be cleaned up (for logging/stats)"""
        from apps.calendars.models import EventState
        
        # Count local events that will be deleted
        local_user_events = calendar.event_states.filter(is_busy_block=False).count()
        local_busy_blocks = calendar.event_states.filter(is_busy_block=True).count()
        
        # Count outbound busy blocks that will be deleted
        user_event_uuids = list(
            calendar.event_states.filter(is_busy_block=False).values_list('uuid', flat=True)
        )
        
        other_calendars = self._get_other_sync_calendars(calendar)
        outbound_busy_blocks = 0
        
        for other_cal in other_calendars:
            outbound_busy_blocks += EventState.objects.filter(
                calendar=other_cal,
                is_busy_block=True,
                source_uuid__in=user_event_uuids
            ).count()
        
        return {
            "local_user_events": local_user_events,
            "local_busy_blocks": local_busy_blocks,
            "outbound_busy_blocks": outbound_busy_blocks,
            "other_calendars_affected": len(other_calendars),
        }

    def _cleanup_outbound_busy_blocks(self, calendar):
        """Remove busy blocks created by this calendar in other calendars (Guilfoyle's batched pattern)"""
        from django.conf import settings
        from apps.calendars.models import EventState
        from apps.calendars.services.google_calendar_client import GoogleCalendarClient
        
        # Get UUIDs of this calendar's user events
        user_event_uuids = list(
            calendar.event_states.filter(is_busy_block=False).values_list('uuid', flat=True)
        )
        
        if not user_event_uuids:
            return 0
        
        other_calendars = self._get_other_sync_calendars(calendar)
        total_cleaned = 0
        batch_size = getattr(settings, 'CLEANUP_BATCH_SIZE', 100)
        
        for other_calendar in other_calendars:
            try:
                # Process in batches to avoid long-running transactions
                calendar_cleaned = self._cleanup_calendar_busy_blocks_batched(
                    other_calendar, user_event_uuids, batch_size
                )
                total_cleaned += calendar_cleaned
                
                self.logger.debug(
                    f"Cleaned {calendar_cleaned} busy blocks from {other_calendar.name}"
                )
                
            except Exception as e:
                self.logger.error(
                    f"Failed to clean busy blocks from {other_calendar.name}: {e}"
                )
        
        return total_cleaned

    def _cleanup_calendar_busy_blocks_batched(self, target_calendar, source_uuids, batch_size):
        """Clean up busy blocks in batches to avoid long transactions"""
        from apps.calendars.models import EventState
        
        total_deleted = 0
        
        while True:
            with transaction.atomic():
                # Get batch of busy block UUIDs to delete
                block_uuids = list(
                    EventState.objects
                    .filter(
                        calendar=target_calendar,
                        is_busy_block=True,
                        source_uuid__in=source_uuids
                    )
                    .values_list('uuid', flat=True)[:batch_size]
                )
                
                if not block_uuids:
                    break
                
                # Get the blocks for Google Calendar deletion
                blocks_to_delete = EventState.objects.filter(uuid__in=block_uuids)
                
                # Delete from Google Calendar first (best effort)
                try:
                    google_cleaned = self._cleanup_google_busy_blocks(
                        blocks_to_delete, target_calendar
                    )
                except Exception as e:
                    # Don't fail database cleanup if Google API fails
                    self.logger.warning(
                        f"Google Calendar cleanup failed (continuing with DB cleanup): {e}"
                    )
                    google_cleaned = 0
                
                # Delete from database
                deleted_count = blocks_to_delete.delete()[0]
                total_deleted += deleted_count
                
                # If we deleted less than batch_size, we're done
                if deleted_count < batch_size:
                    break
        
        return total_deleted

    def _cleanup_calendar_events(self, calendar):
        """Remove all EventState records for this calendar"""
        total_events = calendar.event_states.count()
        
        if total_events > 0:
            try:
                calendar.event_states.all().delete()
                self.logger.debug(f"Deleted {total_events} EventState records from {calendar.name}")
            except Exception as e:
                self.logger.error(f"Failed to delete EventState records from {calendar.name}: {e}")
                raise
        
        return total_events

    def _cleanup_google_busy_blocks(self, busy_blocks_queryset, target_calendar):
        """Delete busy blocks from Google Calendar (Guilfoyle's specific error handling)"""
        from apps.calendars.services.google_calendar_client import GoogleCalendarClient
        from googleapiclient.errors import HttpError
        
        try:
            client = GoogleCalendarClient(target_calendar.calendar_account)
            cleaned_count = 0
            
            for busy_block in busy_blocks_queryset:
                if busy_block.google_event_id:
                    try:
                        success = client.delete_event(
                            target_calendar.google_calendar_id,
                            busy_block.google_event_id
                        )
                        if success:
                            cleaned_count += 1
                        else:
                            self.logger.warning(
                                f"Failed to delete busy block from Google: {busy_block.google_event_id}"
                            )
                    except HttpError as e:
                        # Google API specific errors - these are expected and shouldn't stop cleanup
                        if e.resp.status == 404:
                            # Event already deleted - count as success
                            cleaned_count += 1
                            self.logger.debug(f"Google event already deleted: {busy_block.google_event_id}")
                        elif e.resp.status == 403:
                            # Permission denied - log but continue
                            self.logger.warning(f"Permission denied deleting Google event: {busy_block.google_event_id}")
                        else:
                            self.logger.warning(f"Google API error deleting event {busy_block.google_event_id}: {e}")
                    except Exception as e:
                        # Unexpected errors
                        self.logger.warning(f"Unexpected error deleting Google event {busy_block.google_event_id}: {e}")
            
            return cleaned_count
            
        except Exception as e:
            # Client initialization failed - this should not stop database cleanup
            self.logger.error(f"Failed to initialize Google client for cleanup: {e}")
            return 0

    def _get_other_sync_calendars(self, calendar):
        """Get other sync-enabled calendars for the same user"""
        return list(
            Calendar.objects.filter(
                calendar_account__user=calendar.calendar_account.user,
                sync_enabled=True,
                calendar_account__is_active=True,
            )
            .exclude(id=calendar.id)
            .select_related("calendar_account")
        )

    def _enable_calendar_sync_with_validation(self, calendar):
        """Enable calendar sync with token validation and refresh"""
        try:
            # Check if account is active
            if not calendar.calendar_account.is_active:
                return {
                    "success": False,
                    "error": f"Account {calendar.calendar_account.email} is inactive. Please reconnect your Google account.",
                    "error_type": "account_inactive"
                }

            # Check if token is expired and attempt refresh
            if calendar.calendar_account.is_token_expired:
                self.logger.info(f"Token expired for {calendar.name}, attempting refresh...")
                
                # Import token manager
                from .token_manager import TokenManager
                
                token_manager = TokenManager(calendar.calendar_account)
                credentials = token_manager.get_valid_credentials()
                
                if not credentials:
                    return {
                        "success": False,
                        "error": f"Unable to refresh expired token for {calendar.calendar_account.email}. Please reconnect your Google account.",
                        "error_type": "token_refresh_failed"
                    }
                
                # Refresh calendar account from database to get updated token info
                calendar.calendar_account.refresh_from_db()
                self.logger.info(f"Successfully refreshed token for {calendar.name}")

            # Final validation check
            can_sync, reason = calendar.can_sync()
            if not can_sync:
                return {
                    "success": False,
                    "error": f"Cannot enable sync for {calendar.name}: {reason}",
                    "error_type": "sync_validation_failed"
                }

            # Token is valid, trigger initial sync
            try:
                self._trigger_initial_sync(calendar)
                
                return {
                    "success": True,
                    "message": f"Sync enabled successfully for {calendar.name}",
                    "token_refreshed": calendar.calendar_account.is_token_expired
                }
                
            except Exception as e:
                self.logger.error(f"Initial sync failed for {calendar.name}: {e}")
                return {
                    "success": False,
                    "error": f"Sync enabled but initial sync failed: {str(e)}",
                    "error_type": "initial_sync_failed"
                }

        except Exception as e:
            self.logger.error(f"Error enabling sync for {calendar.name}: {e}")
            return {
                "success": False,
                "error": f"Unexpected error enabling sync: {str(e)}",
                "error_type": "unexpected_error"
            }
