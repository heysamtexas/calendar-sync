"""
Background cleanup service for account disconnections
Implements Guilfoyle-approved pattern with bankruptcy timeout
"""

import logging
from datetime import timedelta
from django.conf import settings
from django.db import transaction
from django.utils import timezone

logger = logging.getLogger(__name__)


class MockCeleryTask:
    """Mock Celery task for development - replace with real Celery in production"""
    def __init__(self, func):
        self.func = func
        
    def delay(self, *args, **kwargs):
        """Queue task for immediate execution in development"""
        return self.func(*args, **kwargs)
    
    def run(self, *args, **kwargs):
        """Execute the task"""
        return self.func(*args, **kwargs)


def _cleanup_account_background_impl(account_id):
    """Background account cleanup with retry and bankruptcy logic"""
    from apps.calendars.models import CalendarAccount
    from apps.calendars.services.calendar_service import CalendarService
    
    try:
        account = CalendarAccount.objects.get(id=account_id)
        logger.info(f"Starting background cleanup for account {account.id} ({account.email})")
        
        # Check bankruptcy conditions
        if not account.can_attempt_cleanup():
            logger.warning(f"Account {account.id} bankruptcy triggered")
            return declare_cleanup_bankruptcy(account)
        
        # Attempt cleanup
        calendar_service = CalendarService()
        cleanup_result = cleanup_account_google_events(account, calendar_service)
        
        if cleanup_result['success']:
            # Complete success - delete account
            with transaction.atomic():
                logger.info(f"Account {account.id} cleanup completed successfully")
                account.status = 'DISCONNECTED'
                account.save(update_fields=['status'])
                account.delete()  # CASCADE removes all related data
            return f"Account {account.id} cleanup completed and deleted"
            
        else:
            # Partial failure - increment retry count
            account.cleanup_retry_count += 1
            account.cleanup_last_error = cleanup_result.get('error', 'Unknown cleanup error')
            account.save(update_fields=['cleanup_retry_count', 'cleanup_last_error'])
            
            logger.info(
                f"Account {account.id} cleanup failed (attempt {account.cleanup_retry_count}), "
                f"will retry later. Error: {account.cleanup_last_error}"
            )
            return f"Account {account.id} cleanup failed, retry scheduled"
            
    except CalendarAccount.DoesNotExist:
        logger.error(f"Account {account_id} not found for cleanup")
        return f"Account {account_id} not found"
        
    except Exception as exc:
        logger.error(f"Account {account_id} cleanup error: {exc}")
        # Update error state
        try:
            account = CalendarAccount.objects.get(id=account_id) 
            account.cleanup_retry_count += 1
            account.cleanup_last_error = str(exc)
            account.save(update_fields=['cleanup_retry_count', 'cleanup_last_error'])
        except:
            pass
        
        return f"Account {account_id} cleanup failed with exception: {exc}"


# Mock task decorator for development
cleanup_account_background = MockCeleryTask(_cleanup_account_background_impl)




def declare_cleanup_bankruptcy(account):
    """Handle cleanup bankruptcy - delete locally and alert"""
    logger.error(f"BANKRUPTCY: Account {account.id} ({account.email}) cleanup failed permanently")
    
    # Update status
    account.status = 'CLEANUP_FAILED'
    account.save(update_fields=['status'])
    
    # Log detailed bankruptcy information
    logger.error(f"""
    Account cleanup bankruptcy details:
    Account: {account.email} (ID: {account.id})
    Retry attempts: {account.cleanup_retry_count}
    Last error: {account.cleanup_last_error}
    Disconnect requested: {account.disconnect_requested_at}
    Age in hours: {account.cleanup_age_hours}
    """)
    
    # In production, this would send email alerts to administrators
    # For now, just log the alert
    logger.critical(f"ALERT: Account {account.email} cleanup bankruptcy - manual intervention may be needed")
    
    # Delete account locally (accept orphaned Google events)
    with transaction.atomic():
        account.delete()
    
    return f"Account {account.id} bankruptcy declared and deleted"


def cleanup_account_google_events(account, calendar_service):
    """Cleanup all Google Calendar events for an account"""
    results = {
        'success': True,
        'calendars_cleaned': 0,
        'events_deleted': 0,
        'errors': []
    }
    
    try:
        # Get all calendars for the account
        calendars = account.calendars.all()
        logger.info(f"Cleaning up {calendars.count()} calendars for account {account.id}")
        
        for calendar in calendars:
            try:
                # Use existing calendar cleanup logic
                calendar_result = calendar_service._execute_gone_gone_cleanup(calendar)
                results['calendars_cleaned'] += 1
                results['events_deleted'] += calendar_result.get('events_deleted', 0)
                logger.debug(f"Cleaned calendar {calendar.name}: {calendar_result}")
                
            except Exception as e:
                error_msg = f"Calendar {calendar.name} cleanup failed: {e}"
                results['errors'].append(error_msg)
                logger.error(error_msg)
                results['success'] = False
        
        if results['errors']:
            results['error'] = '; '.join(results['errors'])
            
        logger.info(f"Account {account.id} cleanup result: {results}")
        return results
        
    except Exception as e:
        logger.error(f"Account {account.id} cleanup failed: {e}")
        return {
            'success': False,
            'error': str(e),
            'calendars_cleaned': 0,
            'events_deleted': 0
        }


def get_accounts_needing_cleanup():
    """Get accounts that need cleanup processing"""
    from apps.calendars.models import CalendarAccount
    from django.db import models
    
    return CalendarAccount.objects.filter(
        status='DISCONNECTING'
    ).filter(
        models.Q(cleanup_retry_count=0) |  # Never tried
        models.Q(disconnect_requested_at__lt=timezone.now() - timedelta(minutes=15))  # Retry after 15min
    )


def process_pending_cleanups():
    """Process all pending account cleanups - for management command"""
    accounts_needing_cleanup = get_accounts_needing_cleanup()
    
    results = []
    for account in accounts_needing_cleanup:
        try:
            result = _cleanup_account_background_impl(account.id)
            results.append(f"Account {account.id}: {result}")
        except Exception as e:
            results.append(f"Account {account.id}: Failed - {e}")
    
    return results