import requests
from django.conf import settings
from django.shortcuts import redirect, render
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from urllib.parse import urlencode
from .models import SocialAccount
from accounts.models import Team, TeamMember  # Imported accounts models

def get_or_create_user_team(user):
    """
    Auto-Healing Helper: Automatically creates a default workspace for the user
    if they don't have one, making the system 100% manual-setup free.
    """
    membership = user.teammemberships.first()
    if membership:
        return membership.team
    
    workspace_name = f"{user.username}'s Workspace"
    team, created = Team.objects.get_or_create(name=workspace_name)
    
    role = 'admin' if user.is_superuser or user.is_staff else 'editor'
    
    TeamMember.objects.get_or_create(
        user=user,
        team=team,
        defaults={'role': role}
    )
    return team

# Load Meta Credentials from settings
FB_APP_ID = getattr(settings, 'FACEBOOK_APP_ID', '')
FB_APP_SECRET = getattr(settings, 'FACEBOOK_APP_SECRET', '')
FB_REDIRECT_URI = getattr(settings, 'FACEBOOK_REDIRECT_URI', 'http://localhost:8000/social/callback/')

@login_required
def connect_mock_social(request):
    active_team = get_or_create_user_team(request.user)
    
    mock_account, created = SocialAccount.objects.get_or_create(
        team=active_team,
        platform='facebook',
        account_name="Nawab's Test FB Page",
        defaults={
            'status': 'connected',
            'platform_account_id': 'mock_page_id_123456',
        }
    )
    mock_account.decrypted_access_token = 'mock_access_token_xyz789'
    mock_account.status = 'connected'
    mock_account.save()

    messages.success(request, f"Successfully connected dummy account: '{mock_account.account_name}'!")
    return redirect('post_create')


@login_required
def facebook_login(request):
    scopes = [
        'pages_show_list',
        'pages_read_engagement',
        'pages_manage_posts',
        'instagram_basic',
        'instagram_content_publish'
    ]
    
    params = {
        'client_id': FB_APP_ID,
        'redirect_uri': FB_REDIRECT_URI,
        'scope': ','.join(scopes),
        'response_type': 'code',
        'state': str(request.user.id)
    }
    
    authorization_url = f"https://www.facebook.com/v20.0/dialog/oauth?{urlencode(params)}"
    return redirect(authorization_url)


@login_required
def facebook_callback(request):
    code = request.GET.get('code')
    state = request.GET.get('state')
    error = request.GET.get('error')

    if error or not code:
        messages.error(request, f"Facebook login was cancelled or failed: {error or 'No response code.'}")
        return redirect('post_list')

    if state != str(request.user.id):
        messages.error(request, "Security token verification failed. Invalid OAuth State.")
        return redirect('post_list')

    # Auto-resolves or silently heals the user's workspace
    active_team = get_or_create_user_team(request.user)

    try:
        token_url = "https://graph.facebook.com/v20.0/oauth/access_token"
        token_params = {
            'client_id': FB_APP_ID,
            'redirect_uri': FB_REDIRECT_URI,
            'client_secret': FB_APP_SECRET,
            'code': code
        }
        token_response = requests.get(token_url, params=token_params, timeout=15)
        token_data = token_response.json()

        if 'access_token' not in token_data:
            error_msg = token_data.get('error', {}).get('message', 'Failed to retrieve access token.')
            messages.error(request, f"OAuth Error: {error_msg}")
            return redirect('post_list')

        short_lived_user_token = token_data['access_token']

        long_lived_url = "https://graph.facebook.com/v20.0/oauth/access_token"
        long_lived_params = {
            'grant_type': 'fb_exchange_token',
            'client_id': FB_APP_ID,
            'client_secret': FB_APP_SECRET,
            'fb_exchange_token': short_lived_user_token
        }
        long_lived_response = requests.get(long_lived_url, params=long_lived_params, timeout=15)
        long_lived_data = long_lived_response.json()
        long_lived_user_token = long_lived_data.get('access_token', short_lived_user_token)

        pages_url = "https://graph.facebook.com/v20.0/me/accounts"
        pages_params = {
            'access_token': long_lived_user_token
        }
        pages_response = requests.get(pages_url, params=pages_params, timeout=15)
        pages_data = pages_response.json()

        if 'data' not in pages_data:
            messages.error(request, "Could not find any Facebook Pages connected to your account.")
            return redirect('post_list')

        connected_pages = []

        for page in pages_data['data']:
            page_name = page['name']
            page_id = page['id']
            page_access_token = page['access_token']

            social_account, created = SocialAccount.objects.update_or_create(
                team=active_team,
                platform='facebook',
                platform_account_id=page_id,
                defaults={
                    'account_name': page_name,
                    'status': 'connected',
                }
            )
            social_account.decrypted_access_token = page_access_token
            social_account.save()
            
            connected_pages.append(page_name)

        if connected_pages:
            messages.success(request, f"Successfully connected: {', '.join(connected_pages)}")
        else:
            messages.warning(request, "No Facebook Pages were registered to connect.")

    except requests.RequestException as e:
        messages.error(request, f"Network error during Meta OAuth: {str(e)}")

    return redirect('post_list')


@login_required
def account_list(request):
    
    active_team = get_or_create_user_team(request.user)
    
    
    accounts = SocialAccount.objects.filter(team=active_team).order_by('-connected_at')
    
    
    membership = request.user.teammemberships.first()
    user_role = membership.role if membership else 'editor'
    
    return render(request, 'social_accounts/account_list.html', {
        'accounts': accounts,
        'user_role': user_role,
        'active_team': active_team
    })