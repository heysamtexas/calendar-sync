"""Token encryption service for secure credential storage"""

import base64
import json
import logging
from typing import Any

from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from django.conf import settings


logger = logging.getLogger(__name__)


class CredentialsError(Exception):
    """Exception raised for credential-related errors"""



class TokenEncryption:
    """Handles secure encryption/decryption of OAuth tokens"""

    @staticmethod
    def _get_encryption_key(salt: bytes = b"calendar_sync_salt") -> bytes:
        """Generate encryption key using PBKDF2"""
        if not hasattr(settings, "SECRET_KEY") or not settings.SECRET_KEY:
            raise CredentialsError("Django SECRET_KEY not configured")

        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=100000,
        )
        key = base64.urlsafe_b64encode(kdf.derive(settings.SECRET_KEY.encode()))
        return key

    @staticmethod
    def encrypt_token(token_data: dict[str, Any]) -> str:
        """Encrypt token data for secure storage"""
        if not token_data:
            raise ValueError("Token data cannot be empty")

        try:
            fernet = Fernet(TokenEncryption._get_encryption_key())
            json_data = json.dumps(token_data, sort_keys=True)
            encrypted = fernet.encrypt(json_data.encode())
            return base64.urlsafe_b64encode(encrypted).decode()
        except Exception as e:
            logger.error(f"Token encryption failed: {e}")
            raise CredentialsError(f"Failed to encrypt token data: {e}") from e

    @staticmethod
    def decrypt_token(encrypted_token: str) -> dict[str, Any]:
        """Decrypt token data from storage"""
        if not encrypted_token or not encrypted_token.strip():
            raise ValueError("Encrypted token cannot be empty")

        try:
            fernet = Fernet(TokenEncryption._get_encryption_key())
            encrypted_bytes = base64.urlsafe_b64decode(encrypted_token.encode())
            decrypted = fernet.decrypt(encrypted_bytes)
            return json.loads(decrypted.decode())
        except Exception as e:
            logger.error(f"Token decryption failed: {e}")
            raise CredentialsError(f"Failed to decrypt token data: {e}") from e


# Convenience functions for backward compatibility
def encrypt_token(token_data: dict[str, Any]) -> str:
    """Encrypt token data for secure storage"""
    return TokenEncryption.encrypt_token(token_data)


def decrypt_token(encrypted_token: str) -> dict[str, Any]:
    """Decrypt token data from storage"""
    return TokenEncryption.decrypt_token(encrypted_token)
