"""Template tags for account status display"""

from django import template

register = template.Library()


@register.filter
def pending_cleanup_count(account):
    """Count calendars pending cleanup for an account"""
    if not hasattr(account, 'calendars'):
        return 0
    return account.calendars.filter(cleanup_pending=True).count()


@register.inclusion_tag('dashboard/partials/account_status_badge.html')
def account_status_badge(account):
    """Render account status badge with cleanup progress"""
    status_config = {
        'ACTIVE': {
            'badge_class': 'bg-success',
            'text': 'Active',
            'description': None,
        },
        'DISCONNECTING': {
            'badge_class': 'bg-warning',
            'text': 'Disconnecting',
            'description': f'Cleanup in progress (attempt {account.cleanup_retry_count + 1})',
        },
        'CLEANUP_FAILED': {
            'badge_class': 'bg-danger', 
            'text': 'Cleanup Failed',
            'description': 'Manual intervention required',
        },
        'DISCONNECTED': {
            'badge_class': 'bg-secondary',
            'text': 'Disconnected',
            'description': None,
        }
    }
    
    config = status_config.get(account.status, status_config['ACTIVE'])
    return {
        'status': account.status,
        **config
    }