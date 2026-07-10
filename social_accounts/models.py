from django.db import models
from django.contrib.auth.models import User
from cryptography.fernet import Fernet
from django.conf import settings


def get_cipher():
    key = settings.FIELD_ENCRYPTION_KEY
    if isinstance(key, str):
        key = key.encode()
    return Fernet(key)


class SocialAccount(models.Model):
    PLATFORM_CHOICES = [
        ('facebook',  'Facebook'),
        ('instagram', 'Instagram'),
        ('twitter',   'Twitter / X'),
        ('threads',   'Threads'),
        ('youtube',   'YouTube'),
        ('tiktok',    'TikTok'),
        ('whatsapp',  'WhatsApp'),
        ('linkedin',  'LinkedIn'),
        ('gmail',     'Gmail'),
    ]

    STATUS_CHOICES = [
        ('connected',    'Connected'),
        ('expired',      'Expired'),
        ('disconnected', 'Disconnected'),
    ]

    # Owner — which admin/user connected this account
    connected_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        related_name='social_accounts'
    )

    platform            = models.CharField(max_length=20, choices=PLATFORM_CHOICES)
    account_name        = models.CharField(max_length=100)
    account_username    = models.CharField(max_length=100, blank=True)
    platform_account_id = models.CharField(max_length=255, null=True, blank=True)
    profile_picture_url = models.URLField(null=True, blank=True)
    status              = models.CharField(max_length=20, choices=STATUS_CHOICES, default='disconnected')

    # Encrypted tokens
    _access_token  = models.TextField(null=True, blank=True, db_column='access_token')
    _refresh_token = models.TextField(null=True, blank=True, db_column='refresh_token')
    token_expiry   = models.DateTimeField(null=True, blank=True)

    # Extra fields
    whatsapp_business_account_id = models.CharField(max_length=255, null=True, blank=True)
    extra_data = models.JSONField(default=dict, blank=True)  # platform-specific extras

    connected_at = models.DateTimeField(auto_now_add=True)
    updated_at   = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('platform', 'platform_account_id')
        ordering = ['platform']

    # --- Token encryption ---

    @property
    def access_token(self):
        if self._access_token:
            try:
                return get_cipher().decrypt(self._access_token.encode()).decode()
            except Exception:
                return self._access_token
        return None

    @access_token.setter
    def access_token(self, value):
        if value:
            try:
                get_cipher().decrypt(value.encode())
                self._access_token = value
            except Exception:
                self._access_token = get_cipher().encrypt(value.encode()).decode()
        else:
            self._access_token = None

    @property
    def refresh_token(self):
        if self._refresh_token:
            try:
                return get_cipher().decrypt(self._refresh_token.encode()).decode()
            except Exception:
                return self._refresh_token
        return None

    @refresh_token.setter
    def refresh_token(self, value):
        if value:
            try:
                get_cipher().decrypt(value.encode())
                self._refresh_token = value
            except Exception:
                self._refresh_token = get_cipher().encrypt(value.encode()).decode()
        else:
            self._refresh_token = None

    def __str__(self):
        return f"{self.account_name} ({self.platform})"