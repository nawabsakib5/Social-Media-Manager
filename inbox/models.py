from django.db import models
from django.conf import settings
from social_accounts.models import SocialAccount


class InboxItem(models.Model):
    TYPE_CHOICES = [
        ('comment', 'Comment'),
        ('message', 'Message'),
        ('whatsapp_message', 'WhatsApp Message'),
    ]

    social_account = models.ForeignKey(SocialAccount, on_delete=models.CASCADE, related_name='inbox_items')
    type = models.CharField(max_length=20, choices=TYPE_CHOICES)
    
    
    item_id = models.CharField(max_length=255, unique=True, null=True, blank=True)
    sender_id = models.CharField(max_length=255, null=True, blank=True) 
    
    sender_name = models.CharField(max_length=100)
    content = models.TextField()
    received_at = models.DateTimeField(null=True, blank=True) 
    is_replied = models.BooleanField(default=False)
    is_read = models.BooleanField(default=False) 

    class Meta:
        ordering = ['-received_at']

    def __str__(self):
        return f"{self.sender_name} ({self.type}): {self.content[:30]}"


class Reply(models.Model):
    inbox_item = models.ForeignKey(InboxItem, on_delete=models.CASCADE, related_name='replies')
    content = models.TextField()
    sent_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, null=True, blank=True)
    sent_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Reply to {self.inbox_item.sender_name}"