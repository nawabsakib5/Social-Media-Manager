# accounts/signals.py
from django.db.models.signals import post_save, post_delete
from django.contrib.auth.signals import user_logged_in, user_logged_out, user_login_failed
from django.dispatch import receiver
from django.conf import settings
from .models import AuditLog, UserProfile


def get_client_ip(request):
    if request is None:
        return None
    x_forwarded = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded:
        return x_forwarded.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR')


def get_user_agent(request):
    if request is None:
        return None
    return request.META.get('HTTP_USER_AGENT', '')[:500]


def log_action(user=None, action='', target='', detail='', request=None):
    AuditLog.objects.create(
        user=user,
        action=action,
        target=target,
        detail=detail,
        ip_address=get_client_ip(request),
        user_agent=get_user_agent(request),
    )


# ── UserProfile Auto-Create ──

@receiver(post_save, sender=settings.AUTH_USER_MODEL)
def create_user_profile(sender, instance, created, **kwargs):
    if created:
        UserProfile.objects.get_or_create(user=instance)


# ── Auth Signals ──

@receiver(user_logged_in)
def on_login(sender, request, user, **kwargs):
    log_action(
        user=user,
        action='login',
        target=f'User: {user.username}',
        request=request
    )


@receiver(user_logged_out)
def on_logout(sender, request, user, **kwargs):
    log_action(
        user=user,
        action='logout',
        target=f'User: {user.username}',
        request=request
    )


@receiver(user_login_failed)
def on_login_failed(sender, credentials, request, **kwargs):
    log_action(
        action='login_failed',
        target=f"Username: {credentials.get('username', 'unknown')}",
        request=request
    )


# ── Post Signals ──

@receiver(post_save, sender='posts.Post')
def on_post_save(sender, instance, created, **kwargs):
    action = 'post_created' if created else 'post_edited'
    log_action(
        user=instance.created_by,
        action=action,
        target=f'Post #{instance.id}',
        detail=instance.content[:100] if instance.content else 'Media only',
    )


@receiver(post_delete, sender='posts.Post')
def on_post_delete(sender, instance, **kwargs):
    log_action(
        user=instance.created_by,
        action='post_deleted',
        target=f'Post #{instance.id}',
        detail=instance.content[:100] if instance.content else 'Media only',
    )


# ── Social Account Signals ──

@receiver(post_save, sender='social_accounts.SocialAccount')
def on_account_save(sender, instance, created, **kwargs):
    if created:
        log_action(
            user=instance.connected_by,
            action='account_connected',
            target=f'{instance.platform}: {instance.account_name}',
        )


@receiver(post_delete, sender='social_accounts.SocialAccount')
def on_account_delete(sender, instance, **kwargs):
    log_action(
        user=instance.connected_by,
        action='account_disconnected',
        target=f'{instance.platform}: {instance.account_name}',
    )


# ── User Management Signals ──

@receiver(post_save, sender=settings.AUTH_USER_MODEL)
def on_user_save(sender, instance, created, **kwargs):
    if created:
        log_action(
            action='user_created',
            target=f'User: {instance.username}',
            detail=f'Email: {instance.email}, Role: {instance.user_type}',
        )


@receiver(post_delete, sender=settings.AUTH_USER_MODEL)
def on_user_delete(sender, instance, **kwargs):
    log_action(
        action='user_deleted',
        target=f'User: {instance.username}',
        detail=f'Email: {instance.email}',
    )