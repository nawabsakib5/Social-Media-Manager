from django.db import models
from accounts.models import Team


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
    connected_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.account_name} ({self.platform})"