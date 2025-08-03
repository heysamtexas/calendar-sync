"""Tests for token encryption service"""

from django.test import TestCase, override_settings

from apps.calendars.services.encryption import (
    CredentialsError,
    TokenEncryption,
    decrypt_token,
    encrypt_token,
)


class TokenEncryptionTest(TestCase):
    """Test token encryption and decryption functionality"""

    def test_encrypt_decrypt_token_success(self):
        """Test successful token encryption and decryption"""
        token_data = {
            "access_token": "test_access_token",
            "refresh_token": "test_refresh_token",
            "expires_in": 3600,
        }

        # Encrypt token
        encrypted_token = encrypt_token(token_data)
        self.assertIsInstance(encrypted_token, str)
        self.assertNotEqual(encrypted_token, str(token_data))

        # Decrypt token
        decrypted_token = decrypt_token(encrypted_token)
        self.assertEqual(decrypted_token, token_data)

    def test_encrypt_empty_token_data(self):
        """Test encryption with empty token data raises error"""
        with self.assertRaises(ValueError):
            encrypt_token({})

        with self.assertRaises(ValueError):
            encrypt_token(None)

    def test_decrypt_empty_token(self):
        """Test decryption with empty token raises error"""
        with self.assertRaises(ValueError):
            decrypt_token("")

        with self.assertRaises(ValueError):
            decrypt_token(None)

        with self.assertRaises(ValueError):
            decrypt_token("   ")

    def test_decrypt_invalid_token(self):
        """Test decryption with invalid token raises error"""
        with self.assertRaises(CredentialsError):
            decrypt_token("invalid_token_data")

    def test_encrypt_decrypt_complex_data(self):
        """Test encryption/decryption with complex nested data"""
        complex_data = {
            "token": "access_token_123",
            "refresh_token": "refresh_token_456",
            "metadata": {
                "scopes": ["calendar", "email"],
                "expires_at": "2024-12-31T23:59:59Z",
                "user_info": {"email": "test@example.com", "verified": True},
            },
        }

        encrypted = encrypt_token(complex_data)
        decrypted = decrypt_token(encrypted)

        self.assertEqual(decrypted, complex_data)

    def test_encryption_deterministic_with_same_data(self):
        """Test that encryption produces different results for same data (using random IV)"""
        token_data = {"token": "test_token"}

        encrypted1 = encrypt_token(token_data)
        encrypted2 = encrypt_token(token_data)

        # Should be different due to random IV in Fernet
        self.assertNotEqual(encrypted1, encrypted2)

        # But both should decrypt to same data
        self.assertEqual(decrypt_token(encrypted1), token_data)
        self.assertEqual(decrypt_token(encrypted2), token_data)

    @override_settings(SECRET_KEY="")
    def test_encryption_missing_secret_key(self):
        """Test encryption fails gracefully with missing SECRET_KEY"""
        with self.assertRaises(CredentialsError):
            encrypt_token({"token": "test"})

    def test_token_encryption_class_methods(self):
        """Test TokenEncryption class methods directly"""
        token_data = {"access_token": "direct_test_token"}

        encrypted = TokenEncryption.encrypt_token(token_data)
        decrypted = TokenEncryption.decrypt_token(encrypted)

        self.assertEqual(decrypted, token_data)

    def test_encryption_handles_unicode(self):
        """Test encryption handles unicode characters properly"""
        token_data = {
            "token": "test_token_🔒",
            "description": "Calendar événement avec accents",
            "emoji": "🗓️📅",
        }

        encrypted = encrypt_token(token_data)
        decrypted = decrypt_token(encrypted)

        self.assertEqual(decrypted, token_data)

    def test_encryption_key_consistency(self):
        """Test that encryption key generation is consistent"""
        # Get two keys with same parameters
        key1 = TokenEncryption._get_encryption_key()
        key2 = TokenEncryption._get_encryption_key()

        # Should be identical
        self.assertEqual(key1, key2)

    def test_large_token_data(self):
        """Test encryption with large token data"""
        large_data = {
            "token": "x" * 1000,
            "refresh_token": "y" * 1000,
            "large_field": "z" * 5000,
        }

        encrypted = encrypt_token(large_data)
        decrypted = decrypt_token(encrypted)

        self.assertEqual(decrypted, large_data)
