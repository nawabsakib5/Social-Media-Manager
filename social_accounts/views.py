from django.shortcuts import render

# Create your views here.
from django.shortcuts import redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from .models import SocialAccount

@login_required
def connect_mock_social(request):
    
    membership = request.user.teammemberships.first()
    
    if not membership:
        messages.error(request, "You do not have an active team. Please create a team first.")
        return redirect('post_list')

    active_team = membership.team

    
    mock_account, created = SocialAccount.objects.get_or_create(
        team=active_team,
        platform='facebook',
        account_name="Nawab's Test FB Page",
        defaults={
            'status': 'connected',
            'platform_account_id': 'mock_page_id_123456',
            'access_token': 'mock_access_token_xyz789',
        }
    )

    if created:
        messages.success(request, f"Successfully connected dummy account: '{mock_account.account_name}'!")
    else:
        mock_account.status = 'connected'
        mock_account.save()
        messages.info(request, f"'{mock_account.account_name}' is already connected.")

    
    return redirect('post_create')