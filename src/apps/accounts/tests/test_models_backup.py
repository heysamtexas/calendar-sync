from django.contrib.auth.models import User
from django.test import TestCase

from apps.accounts.models import UserProfile


class UserProfileModelTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="testuser", email="test@example.com", password="testpass123"
        )

    def test_user_profile_creation(self):
        """Test creating a user profile"""
        profile = UserProfile.objects.create(
            user=self.user, timezone="America/New_York", sync_enabled=True
        )
        self.assertEqual(profile.user, self.user)
        self.assertEqual(profile.timezone, "America/New_York")
        self.assertTrue(profile.sync_enabled)
        self.assertIsNotNone(profile.created_at)
        self.assertIsNotNone(profile.updated_at)

    def test_user_profile_str(self):
        """Test string representation of UserProfile"""
        profile = UserProfile.objects.create(user=self.user)
        self.assertEqual(str(profile), f"Profile for {self.user.username}")

    def test_default_values(self):
        """Test default values for UserProfile"""
        profile = UserProfile.objects.create(user=self.user)
        self.assertEqual(profile.timezone, "UTC")
        self.assertTrue(profile.sync_enabled)

    def test_one_to_one_relationship(self):
        """Test one-to-one relationship with User"""
        profile = UserProfile.objects.create(user=self.user)
        self.assertEqual(self.user.profile, profile)

    def test_verbose_name(self):
        """Test model verbose names"""
        self.assertEqual(UserProfile._meta.verbose_name, "User Profile")
        self.assertEqual(UserProfile._meta.verbose_name_plural, "User Profiles")
