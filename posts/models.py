from django.db import models
from social_accounts.models import SocialAccount
from django.conf import settings


class Post(models.Model):
    STATUS_CHOICES = [
        ('draft',      'Draft'),
        ('scheduled',  'Scheduled'),
        ('processing', 'Processing'),
        ('published',  'Published'),
        ('failed',     'Failed'),
    ]

    social_accounts = models.ManyToManyField(
        'social_accounts.SocialAccount',
        through='PostPlatformStatus',
        related_name='posts'
    )
    content        = models.TextField(blank=True, null=True)
    scheduled_time = models.DateTimeField(null=True, blank=True)
    status         = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft')
    created_by     = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='created_posts',
        null=True, blank=True
    )
    created_at = models.DateTimeField(auto_now_add=True)

    def get_media_items(self):
        return self.media_items.all()

    def get_first_media(self):
        return self.media_items.first()

    def has_media(self):
        return self.media_items.exists()

    def __str__(self):
        return f"{self.content[:30] if self.content else 'Media only post'}"


class PostMedia(models.Model):
    MEDIA_TYPE_CHOICES = [
        ('image', 'Image'),
        ('video', 'Video'),
    ]
    post       = models.ForeignKey(Post, on_delete=models.CASCADE, related_name='media_items')
    url        = models.URLField(max_length=500)
    media_type = models.CharField(max_length=10, choices=MEDIA_TYPE_CHOICES, default='image')
    order      = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['order', 'created_at']

    def __str__(self):
        return f"{self.media_type} for Post #{self.post_id}"


class PostPlatformStatus(models.Model):
    STATUS_CHOICES = [
        ('scheduled',  'Scheduled'),
        ('processing', 'Processing'),
        ('published',  'Published'),
        ('failed',     'Failed'),
    ]

    post             = models.ForeignKey(Post, on_delete=models.CASCADE, related_name='platform_statuses')
    social_account   = models.ForeignKey(SocialAccount, on_delete=models.CASCADE)
    status           = models.CharField(max_length=20, choices=STATUS_CHOICES, default='scheduled')
    platform_post_id = models.CharField(max_length=255, null=True, blank=True)
    error_message    = models.TextField(null=True, blank=True)
    published_at     = models.DateTimeField(null=True, blank=True)

    class Meta:
        unique_together = ('post', 'social_account')

    def __str__(self):
        return f"{self.post} → {self.social_account} ({self.status})"


class ExternalPost(models.Model):
    """Meta Business Suite বা অন্য জায়গা থেকে করা posts sync করার জন্য"""
    PLATFORM_CHOICES = [
        ('facebook',  'Facebook'),
        ('instagram', 'Instagram'),
        ('linkedin',  'LinkedIn'),
        ('twitter',   'Twitter/X'),
        ('youtube',   'YouTube'),
        ('tiktok',    'TikTok'),
        ('threads',   'Threads'),
        ('pinterest', 'Pinterest'),
        ('telegram',  'Telegram'),
        
    ]
    social_account   = models.ForeignKey(
        SocialAccount,
        on_delete=models.CASCADE,
        related_name='external_posts'
    )
    platform         = models.CharField(max_length=20, choices=PLATFORM_CHOICES)
    external_post_id = models.CharField(max_length=255)
    content          = models.TextField(blank=True, null=True)
    media_url        = models.TextField(blank=True, null=True)   # ✅ TextField
    media_type       = models.CharField(max_length=20, blank=True, null=True)
    permalink_url    = models.TextField(blank=True, null=True)   # ✅ TextField

    # Analytics
    likes            = models.IntegerField(default=0)
    comments         = models.IntegerField(default=0)
    shares           = models.IntegerField(default=0)
    reach            = models.IntegerField(default=0)
    impressions      = models.IntegerField(default=0)

    posted_at        = models.DateTimeField(null=True, blank=True)
    synced_at        = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('social_account', 'external_post_id')
        ordering = ['-posted_at']

    def __str__(self):
        return f"{self.platform} post {self.external_post_id} ({self.social_account.account_name})"