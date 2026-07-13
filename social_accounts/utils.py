# social_accounts/utils.py

from cryptography.fernet import Fernet
from django.conf import settings
import base64
import os

def get_encryption_key():
    """Encryption key পাওয়া"""
    key = settings.FIELD_ENCRYPTION_KEY
    
    # যদি key স্ট্রিং হয়, এনকোড করুন
    if isinstance(key, str):
        key = key.encode()
    
    # যদি key না থাকে, নতুন generate করুন
    if not key:
        key = Fernet.generate_key()
        print(f"⚠️ No encryption key found. Generated new key: {key.decode()}")
        print("Please add this to your .env file as FIELD_ENCRYPTION_KEY")
    
    return key

def encrypt_token(token):
    """Token এনক্রিপ্ট করা"""
    if not token:
        return None
    
    try:
        key = get_encryption_key()
        cipher = Fernet(key)
        encrypted = cipher.encrypt(token.encode())
        return encrypted.decode()
    except Exception as e:
        print(f"❌ Encryption error: {e}")
        return token  # যদি এনক্রিপ্ট না হয়, প্লেইন টেক্সট রিটার্ন করুন

def decrypt_token(encrypted_token):
    """Token ডিক্রিপ্ট করা"""
    if not encrypted_token:
        return None
    
    try:
        key = get_encryption_key()
        cipher = Fernet(key)
        decrypted = cipher.decrypt(encrypted_token.encode())
        return decrypted.decode()
    except Exception as e:
        print(f"❌ Decryption error: {e}")
        # যদি ডিক্রিপ্ট না হয়, ধরে নিই প্লেইন টেক্সট
        return encrypted_token