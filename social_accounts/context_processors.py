from .models import SocialAccount

def connected_accounts(request):
    if not request.user.is_authenticated:
        return {
            'connected_accounts': [],
            'unread_inbox_count': 0,
        }

    if request.user.is_superuser or getattr(request.user, 'user_type', None) == 'admin':
        accounts = SocialAccount.objects.filter(status='connected')
    else:
        accounts = SocialAccount.objects.filter(status='connected', permitted_users=request.user)

    # Unread inbox count
    unread_inbox_count = 0
    try:
        from inbox.models import InboxItem
        if request.user.is_superuser or getattr(request.user, 'user_type', None) == 'admin':
            unread_inbox_count = InboxItem.objects.filter(is_read=False).count()
        else:
            unread_inbox_count = InboxItem.objects.filter(
                social_account__permitted_users=request.user,
                is_read=False
            ).count()
    except Exception:
        pass

    return {
        'connected_accounts': accounts.order_by('platform'),
        'unread_inbox_count': unread_inbox_count,
    }