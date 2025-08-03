from django.conf import settings
from django.db import models


class UserProfile(models.Model):
    """Extended user profile for calendar sync preferences"""

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="profile"
    )
    timezone = models.CharField(
        max_length=50,
        default="UTC",
        help_text="User's primary timezone for calendar operations",
    )
    sync_enabled = models.BooleanField(
        default=True, help_text="Global sync enable/disable for this user"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "User Profile"
        verbose_name_plural = "User Profiles"

    def __str__(self):
        return f"Profile for {self.user.username}"
