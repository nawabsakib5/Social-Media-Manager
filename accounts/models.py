# accounts/models.py
from django.db import models
from django.contrib.auth.models import AbstractUser
from django.conf import settings


class CustomUserModel(AbstractUser):
    full_name = models.CharField(max_length=100, null=True, blank=True)
    phone     = models.CharField(max_length=20,  null=True, blank=True)

    USER_TYPE_CHOICES = [
        ('admin', 'Admin'),
        ('user',  'User'),
    ]
    user_type = models.CharField(
        max_length=20,
        choices=USER_TYPE_CHOICES,
        default='user',
        null=True, blank=True
    )

    failed_login_attempts = models.IntegerField(default=0)
    locked_until          = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return self.username

    @property
    def is_app_admin(self):
        return self.user_type == 'admin' or self.is_superuser or self.is_staff


class UserProfile(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='profile'
    )
    avatar     = models.ImageField(upload_to='avatars/', null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.user.username

    @property
    def is_admin(self):
        return self.user.is_superuser or self.user.is_staff


class Invitation(models.Model):
    email      = models.EmailField(unique=True)
    token      = models.CharField(max_length=64, unique=True)
    user_type  = models.CharField(max_length=10, choices=[('admin', 'Admin'), ('user', 'User')], default='user')
    permitted_accounts = models.JSONField(default=list, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    is_accepted = models.BooleanField(default=False)

    def __str__(self):
        return f"Invitation to {self.email} ({self.user_type})"


class AuditLog(models.Model):
    ACTION_CHOICES = [
        # Auth
        ('login',               'User Login'),
        ('logout',              'User Logout'),
        ('login_failed',        'Login Failed'),
        ('account_locked',      'Account Locked'),
        # User management
        ('user_created',        'User Created'),
        ('user_deleted',        'User Deleted'),
        ('user_role_changed',   'User Role Changed'),
        ('user_activated',      'User Activated'),
        ('user_deactivated',    'User Deactivated'),
        ('password_changed',    'Password Changed'),
        ('permission_updated',  'Permission Updated'),
        # Posts
        ('post_created',        'Post Created'),
        ('post_published',      'Post Published'),
        ('post_edited',         'Post Edited'),
        ('post_deleted',        'Post Deleted'),
        ('post_failed',         'Post Failed'),
        # Social accounts
        ('account_connected',   'Account Connected'),
        ('account_disconnected','Account Disconnected'),
        # Inbox
        ('inbox_replied',       'Inbox Replied'),
        ('inbox_marked_read',   'Inbox Marked Read'),
        # Invitation
        ('invitation_sent',     'Invitation Sent'),
        ('invitation_accepted', 'Invitation Accepted'),
    ]

    user        = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='audit_logs'
    )
    action      = models.CharField(max_length=50, choices=ACTION_CHOICES)
    target      = models.CharField(max_length=255, null=True, blank=True)  # e.g. "Post #12", "User: sakib"
    detail      = models.TextField(null=True, blank=True)                  # extra info
    ip_address  = models.GenericIPAddressField(null=True, blank=True)
    user_agent  = models.CharField(max_length=500, null=True, blank=True)
    timestamp   = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-timestamp']
        indexes  = [
            models.Index(fields=['-timestamp']),
            models.Index(fields=['user', '-timestamp']),
            models.Index(fields=['action']),
        ]

    def __str__(self):
        user_str = self.user.username if self.user else 'System'
        return f"[{self.timestamp:%Y-%m-%d %H:%M}] {user_str} → {self.action}"