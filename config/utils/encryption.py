from cryptography.fernet import Fernet
from django.conf import settings

def get_encryptor():
    key = getattr(settings, 'FIELD_ENCRYPTION_KEY', None)
    if not key:
        raise ValueError("FIELD_ENCRYPTION_KEY is not defined in settings or env file.")
    return Fernet(key.encode())

def encrypt_token(plain_text: str) -> str:
    if not plain_text:
        return ""
    f = get_encryptor()
    return f.encrypt(plain_text.encode()).decode()

def decrypt_token(cipher_text: str) -> str:
    if not cipher_text:
        return ""
    f = get_encryptor()
    return f.decrypt(cipher_text.encode()).decode()