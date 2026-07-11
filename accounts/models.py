# accounts/models.py
from django.db import models
from django.contrib.auth.models import AbstractUser
from django.conf import settings



from django.db import models
from django.contrib.auth.models import AbstractUser


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
    avatar = models.ImageField(upload_to='avatars/', null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.user.username

    @property
    def is_admin(self):
        return self.user.is_superuser or self.user.is_staff