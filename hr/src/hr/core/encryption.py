"""
Field-level encryption utilities for sensitive employee data.
Uses Fernet symmetric encryption (AES 128 in CBC mode).
"""
from cryptography.fernet import Fernet
from typing import Optional
import base64
import os


class FieldEncryption:
    """Handles encryption and decryption of sensitive fields."""

    def __init__(self, encryption_key: Optional[str] = None):
        """
        Initialize encryption handler.

        Args:
            encryption_key: Base64-encoded Fernet key. If None, uses ENCRYPTION_KEY env var.
        """
        if encryption_key is None:
            encryption_key = os.getenv('ENCRYPTION_KEY')

        if not encryption_key:
            raise ValueError(
                "ENCRYPTION_KEY environment variable must be set. "
                "Generate one using: python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())'"
            )

        # Ensure key is bytes
        if isinstance(encryption_key, str):
            encryption_key = encryption_key.encode()

        self.fernet = Fernet(encryption_key)

    def encrypt(self, plaintext: Optional[str]) -> Optional[str]:
        """
        Encrypt a plaintext string.

        Args:
            plaintext: String to encrypt. Can be None or empty.

        Returns:
            Encrypted string (base64 encoded), or None if input was None/empty.
        """
        if not plaintext:
            return None

        try:
            # Convert to bytes, encrypt, return as string
            encrypted_bytes = self.fernet.encrypt(plaintext.encode('utf-8'))
            return encrypted_bytes.decode('utf-8')
        except Exception as e:
            raise ValueError(f"Encryption failed: {str(e)}")

    def decrypt(self, ciphertext: Optional[str]) -> Optional[str]:
        """
        Decrypt an encrypted string.

        Args:
            ciphertext: Encrypted string (base64 encoded). Can be None or empty.

        Returns:
            Decrypted plaintext string, or None if input was None/empty.
        """
        if not ciphertext:
            return None

        try:
            # Convert to bytes, decrypt, return as string
            decrypted_bytes = self.fernet.decrypt(ciphertext.encode('utf-8'))
            return decrypted_bytes.decode('utf-8')
        except Exception as e:
            # If decryption fails, might be unencrypted legacy data
            # Return as-is for backward compatibility during migration
            return ciphertext

    def is_encrypted(self, value: Optional[str]) -> bool:
        """
        Check if a value appears to be encrypted.

        Args:
            value: String to check

        Returns:
            True if value appears to be Fernet-encrypted, False otherwise.
        """
        if not value:
            return False

        try:
            # Fernet tokens are base64 encoded and start with 'gAAAAA'
            # Try to decrypt - if it works, it's encrypted
            self.fernet.decrypt(value.encode('utf-8'))
            return True
        except Exception:
            return False


def generate_encryption_key() -> str:
    """
    Generate a new Fernet encryption key.

    Returns:
        Base64-encoded encryption key as string.
    """
    return Fernet.generate_key().decode('utf-8')


# Global encryption instance (initialized on first use)
_encryption_instance: Optional[FieldEncryption] = None


def get_encryption() -> FieldEncryption:
    """
    Get the global encryption instance (singleton pattern).

    Returns:
        FieldEncryption instance.
    """
    global _encryption_instance
    if _encryption_instance is None:
        _encryption_instance = FieldEncryption()
    return _encryption_instance


def encrypt_value(plaintext: Optional[str]) -> Optional[str]:
    """
    Convenience function to encrypt a value using the global encryption instance.
    
    Args:
        plaintext: String to encrypt
        
    Returns:
        Encrypted string or None
    """
    if not plaintext:
        return None
    return get_encryption().encrypt(plaintext)


def decrypt_value(ciphertext: Optional[str]) -> Optional[str]:
    """
    Convenience function to decrypt a value using the global encryption instance.
    
    Args:
        ciphertext: Encrypted string
        
    Returns:
        Decrypted string or None
    """
    if not ciphertext:
        return None
    return get_encryption().decrypt(ciphertext)
