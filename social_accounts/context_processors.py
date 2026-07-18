
from .models import SocialAccount

def connected_accounts(request):
    
    if not request.user.is_authenticated:
        return {'connected_accounts': []}
        
    
    if request.user.is_superuser or getattr(request.user, 'user_type', None) == 'admin':
        accounts = SocialAccount.objects.filter(status='connected')
    else:
        
        accounts = SocialAccount.objects.filter(status='connected', permitted_users=request.user)
        
    return {
        'connected_accounts': accounts.order_by('platform')
    }