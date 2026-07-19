# social_accounts/utils.py
import os
import base64
import hashlib
from cryptography.fernet import Fernet
from django.conf import settings



def get_encryption_key():
    
    key = settings.FIELD_ENCRYPTION_KEY
    
    if isinstance(key, str):
        key = key.encode()
    
    
    if not key:
        key = Fernet.generate_key()
        print(f"⚠️ No encryption key found. Generated new key: {key.decode()}")
        print("Please add this to your .env file as FIELD_ENCRYPTION_KEY")
    
    return key


def encrypt_token(token):
    
    if not token:
        return None
    
    try:
        key = get_encryption_key()
        cipher = Fernet(key)
        encrypted = cipher.encrypt(token.encode())
        return encrypted.decode()
    except Exception as e:
        print(f"❌ Encryption error: {e}")
        return token


def decrypt_token(encrypted_token):
    
    if not encrypted_token:
        return None
    
    try:
        key = get_encryption_key()
        cipher = Fernet(key)
        decrypted = cipher.decrypt(encrypted_token.encode())
        return decrypted.decode()
    except Exception as e:
        print(f"❌ Decryption error: {e}")
        return encrypted_token


# ── ২. নতুন যুক্ত হওয়া টুইটার OAuth 2.0 PKCE মেথড (টুইটার সংযোগের জন্য) ──

def generate_pkce_pair():
    
    
    verifier = base64.urlsafe_b64encode(os.urandom(32)).decode('utf-8').replace('=', '')
    
    
    sha256_hash = hashlib.sha256(verifier.encode('utf-8')).digest()
    challenge = base64.urlsafe_b64encode(sha256_hash).decode('utf-8').replace('=', '')
    
    return verifier, challenge