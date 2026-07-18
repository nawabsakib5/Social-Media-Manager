from django.db import models
from django.conf import settings
from cryptography.fernet import Fernet
import base64
import os

User = settings.AUTH_USER_MODEL


def get_cipher():
    key = settings.FIELD_ENCRYPTION_KEY
    if isinstance(key, str):
        key = key.encode()
    return Fernet(key)


class SocialAccount(models.Model):
    PLATFORM_CHOICES = [
        ('facebook', 'Facebook'),
        ('instagram', 'Instagram'),
        ('twitter', 'Twitter / X'),
        ('threads', 'Threads'),
        ('youtube', 'YouTube'),
        ('tiktok', 'TikTok'),
        ('whatsapp', 'WhatsApp'),
        ('linkedin', 'LinkedIn'),
        ('gmail', 'Gmail'),
    ]

    STATUS_CHOICES = [
        ('connected', 'Connected'),
        ('expired', 'Expired'),
        ('disconnected', 'Disconnected'),
    ]

    # Basic Info
    platform = models.CharField(max_length=20, choices=PLATFORM_CHOICES)
    account_name = models.CharField(max_length=100)
    account_username = models.CharField(max_length=100, blank=True)
    platform_account_id = models.CharField(max_length=255, null=True, blank=True)
    profile_picture_url = models.URLField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='disconnected')

    # Encrypted tokens (using property methods for encryption)
    _access_token = models.TextField(null=True, blank=True, db_column='access_token')
    _refresh_token = models.TextField(null=True, blank=True, db_column='refresh_token')
    token_expiry = models.DateTimeField(null=True, blank=True)

    # Extra fields for platform-specific data
    whatsapp_business_account_id = models.CharField(max_length=255, null=True, blank=True)
    extra_data = models.JSONField(default=dict, blank=True)

    # Relations
    connected_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='social_accounts'
    )
    
    
    permitted_users = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        blank=True,
        related_name='permitted_accounts'
    )

    
    connected_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('platform', 'platform_account_id')
        ordering = ['platform', 'account_name']
        indexes = [
            models.Index(fields=['platform', 'status']),
            models.Index(fields=['connected_by', 'platform']),
        ]

    def __str__(self):
        return f"{self.account_name} ({self.platform})"

    

    @property
    def access_token(self):
        if not self._access_token:
            return None
        try:
            return get_cipher().decrypt(self._access_token.encode()).decode()
        except Exception:
            
            return self._access_token

    @access_token.setter
    def access_token(self, value):
        if not value:
            self._access_token = None
            return
        
        try:
            
            get_cipher().decrypt(value.encode())
            self._access_token = value
        except Exception:
            
            self._access_token = get_cipher().encrypt(value.encode()).decode()

    @property
    def refresh_token(self):
        if not self._refresh_token:
            return None
        try:
            return get_cipher().decrypt(self._refresh_token.encode()).decode()
        except Exception:
            return self._refresh_token

    @refresh_token.setter
    def refresh_token(self, value):
        if not value:
            self._refresh_token = None
            return
        
        try:
            get_cipher().decrypt(value.encode())
            self._refresh_token = value
        except Exception:
            self._refresh_token = get_cipher().encrypt(value.encode()).decode()

    
    def get_token(self):
        return self.access_token

    def set_token(self, token):
        self.access_token = token
        return True

    def is_expired(self):
        if not self.token_expiry:
            return False
        from django.utils import timezone
        return timezone.now() >= self.token_expiry

    def is_connected(self):
        return self.status == 'connected'

    def disconnect(self):
        self.status = 'disconnected'
        self.save()

    def get_platform_display_name(self):
        return dict(self.PLATFORM_CHOICES).get(self.platform, self.platform)