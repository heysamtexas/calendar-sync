"""Base service class for business logic operations"""

import logging

from django.core.exceptions import PermissionDenied


logger = logging.getLogger(__name__)


class BaseService:
    """Base class for all business services"""

    def __init__(self, user=None):
        self.user = user
        self.logger = logger.getChild(self.__class__.__name__)

    def _validate_user_permission(self, obj, user_field="user"):
        """Validate user has permission for operation"""
        if not self.user:
            raise PermissionDenied("User required for this operation")

        # Handle nested user field (e.g., 'calendar_account__user')
        if "__" in user_field:
            obj_user = obj
            for field in user_field.split("__"):
                obj_user = getattr(obj_user, field)
        else:
            obj_user = getattr(obj, user_field)

        if obj_user != self.user:
            raise PermissionDenied(
                f"User {self.user.username} cannot access this resource"
            )

    def _log_operation(self, operation, **kwargs):
        """Standardized operation logging"""
        self.logger.info(
            f"Operation: {operation}",
            extra={
                "user_id": self.user.id if self.user else None,
                "user_name": self.user.username if self.user else None,
                **kwargs,
            },
        )

    def _handle_error(self, error, operation, **context):
        """Standardized error handling"""
        self.logger.error(
            f"Error in {operation}: {error!s}",
            extra={
                "error_type": type(error).__name__,
                "user_id": self.user.id if self.user else None,
                **context,
            },
            exc_info=True,
        )
        raise


class ServiceError(Exception):
    """Base exception for service layer errors"""


class ResourceNotFoundError(ServiceError):
    """Resource not found in service operation"""


class BusinessLogicError(ServiceError):
    """Business logic validation error"""


class ExternalServiceError(ServiceError):
    """Error from external service (Google API, etc.)"""
