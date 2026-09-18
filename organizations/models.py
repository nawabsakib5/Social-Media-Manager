from django.db import models
from django.conf import settings


class Organization(models.Model):
    name = models.CharField(max_length=150)
    slug = models.SlugField(max_length=160, unique=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='organizations_created'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    is_active = models.BooleanField(default=True)

    members = models.ManyToManyField(
        settings.AUTH_USER_MODEL, through='Membership', related_name='organizations',
        through_fields=('organization', 'user')
    )

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name


class Membership(models.Model):
    ROLE_OWNER = 'owner'
    ROLE_ADMIN = 'admin'
    ROLE_EDITOR = 'editor'
    ROLE_APPROVER = 'approver'
    ROLE_VIEWER = 'viewer'

    ROLE_CHOICES = [
        (ROLE_OWNER, 'Owner'),
        (ROLE_ADMIN, 'Admin'),
        (ROLE_EDITOR, 'Editor'),
        (ROLE_APPROVER, 'Approver'),
        (ROLE_VIEWER, 'Viewer'),
    ]

    ROLE_RANK = {
        ROLE_VIEWER: 0,
        ROLE_APPROVER: 1,
        ROLE_EDITOR: 2,
        ROLE_ADMIN: 3,
        ROLE_OWNER: 4,
    }

    organization = models.ForeignKey(
        Organization, on_delete=models.CASCADE, related_name='memberships'
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='memberships'
    )
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default=ROLE_VIEWER)
    invited_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='memberships_invited'
    )
    joined_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('organization', 'user')
        ordering = ['-role']

    def __str__(self):
        return f"{self.user} @ {self.organization} ({self.get_role_display()})"

    def has_at_least(self, role):
        return self.ROLE_RANK[self.role] >= self.ROLE_RANK[role]