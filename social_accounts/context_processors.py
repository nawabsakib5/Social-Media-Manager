from .models import SocialAccount


def connected_accounts(request):
    if request.user.is_authenticated:
        accounts = SocialAccount.objects.filter(status='connected').order_by('platform')
        return {'connected_accounts': accounts}
    return {'connected_accounts': []}