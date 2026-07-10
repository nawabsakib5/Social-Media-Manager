from django.db import models
from django.contrib.auth.models import User
from social_accounts.models import SocialAccount


class Post(models.Model):
    STATUS_CHOICES = [
        ('draft',     'Draft'),
        ('scheduled', 'Scheduled'),
        ('published', 'Published'),
        ('failed',    'Failed'),
    ]

    social_accounts = models.ManyToManyField(
        SocialAccount,
        through='PostPlatformStatus',
        related_name='posts'
    )
    content        = models.TextField()
    media_file     = models.FileField(upload_to='post_media/', null=True, blank=True)
    scheduled_time = models.DateTimeField(null=True, blank=True)
    status         = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft')
    created_by     = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    created_at     = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.content[:30]}"


class PostPlatformStatus(models.Model):
    STATUS_CHOICES = [
        ('scheduled',  'Scheduled'),
        ('processing', 'Processing'),
        ('published',  'Published'),
        ('failed',     'Failed'),
    ]

    post           = models.ForeignKey(Post, on_delete=models.CASCADE, related_name='platform_statuses')
    social_account = models.ForeignKey(SocialAccount, on_delete=models.CASCADE)
    status         = models.CharField(max_length=20, choices=STATUS_CHOICES, default='scheduled')
    platform_post_id = models.CharField(max_length=255, null=True, blank=True)
    error_message  = models.TextField(null=True, blank=True)
    published_at   = models.DateTimeField(null=True, blank=True)

    class Meta:
        unique_together = ('post', 'social_account')

    def __str__(self):
        return f"{self.post} → {self.social_account} ({self.status})"