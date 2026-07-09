from django.db import models
from django.conf import settings
from accounts.models import Team
from cryptography.fernet import Fernet


def get_cipher():
    key = settings.FIELD_ENCRYPTION_KEY
    if isinstance(key, str):
        key = key.encode()
    return Fernet(key)


class SocialAccount(models.Model):
    PLATFORM_CHOICES = [
        ('facebook', 'Facebook'),
        ('instagram', 'Instagram'),
        ('whatsapp', 'WhatsApp'),
    ]

    STATUS_CHOICES = [
        ('connected', 'Connected'),
        ('expired', 'Expired'),
        ('disconnected', 'Disconnected'),
    ]

    team = models.ForeignKey(Team, on_delete=models.CASCADE)
    platform = models.CharField(max_length=20, choices=PLATFORM_CHOICES)
    account_name = models.CharField(max_length=100)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='disconnected')

    platform_account_id = models.CharField(max_length=255, null=True, blank=True)
    _access_token = models.TextField(null=True, blank=True, db_column='access_token')
    _refresh_token = models.TextField(null=True, blank=True, db_column='refresh_token')
    token_expiry = models.DateTimeField(null=True, blank=True)

    connected_at = models.DateTimeField(auto_now_add=True)

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
                # Already encrypted check
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