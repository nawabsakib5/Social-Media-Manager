import requests
from django.conf import settings
from django.shortcuts import redirect, render
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from urllib.parse import urlencode
from .models import SocialAccount

FB_APP_ID       = getattr(settings, 'FACEBOOK_APP_ID', '')
FB_APP_SECRET   = getattr(settings, 'FACEBOOK_APP_SECRET', '')
FB_REDIRECT_URI = getattr(settings, 'FACEBOOK_REDIRECT_URI', 'http://localhost:8000/social/callback/')


@login_required
def account_list(request):
    PLATFORMS = [
        'facebook', 'instagram', 'twitter', 'threads',
        'youtube', 'tiktok', 'whatsapp', 'linkedin', 'gmail',
    ]
    connected = {acc.platform: acc for acc in SocialAccount.objects.all()}
    platform_data = [
        {'name': p, 'account': connected.get(p)}
        for p in PLATFORMS
    ]
    return render(request, 'social_accounts/account_list.html', {
        'accounts': SocialAccount.objects.all().order_by('platform'),
        'platform_data': platform_data,
    })

@login_required
def facebook_login(request):
    scopes = [
        'pages_show_list',
        'pages_read_engagement',
        'pages_manage_posts',
        'business_management',
        'instagram_basic',
        'instagram_content_publish',
    ]
    params = {
        'client_id':     FB_APP_ID,
        'redirect_uri':  FB_REDIRECT_URI,
        'scope':         ','.join(scopes),
        'response_type': 'code',
        'state':         str(request.user.id),
    }
    return redirect(f"https://www.facebook.com/v21.0/dialog/oauth?{urlencode(params)}")


@login_required
def facebook_callback(request):
    code  = request.GET.get('code')
    state = request.GET.get('state')
    error = request.GET.get('error')

    if error or not code:
        messages.error(request, f"Facebook login failed: {error or 'No code received.'}")
        return redirect('post_list')

    if state != str(request.user.id):
        messages.error(request, "Security check failed. Invalid OAuth state.")
        return redirect('post_list')

    try:
        # Step A: short-lived token
        token_res = requests.get(
            "https://graph.facebook.com/v21.0/oauth/access_token",
            params={
                'client_id':     FB_APP_ID,
                'redirect_uri':  FB_REDIRECT_URI,
                'client_secret': FB_APP_SECRET,
                'code':          code,
            },
            timeout=15
        ).json()

        if 'access_token' not in token_res:
            messages.error(request, token_res.get('error', {}).get('message', 'Token exchange failed.'))
            return redirect('post_list')

        short_token = token_res['access_token']

        # Step B: long-lived token (60 days)
        long_res = requests.get(
            "https://graph.facebook.com/v21.0/oauth/access_token",
            params={
                'grant_type':       'fb_exchange_token',
                'client_id':        FB_APP_ID,
                'client_secret':    FB_APP_SECRET,
                'fb_exchange_token': short_token,
            },
            timeout=15
        ).json()
        long_token = long_res.get('access_token', short_token)

        # Step C: get Facebook pages
        pages_data = requests.get(
            "https://graph.facebook.com/v21.0/me/accounts",
            params={'access_token': long_token},
            timeout=15
        ).json()

        if 'data' not in pages_data:
            messages.error(request, "No Facebook Pages found on this account.")
            return redirect('post_list')

        connected = []
        for page in pages_data['data']:
            account, _ = SocialAccount.objects.update_or_create(
                platform='facebook',
                platform_account_id=page['id'],
                defaults={
                    'account_name':  page['name'],
                    'status':        'connected',
                    'connected_by':  request.user,
                }
            )
            account.access_token = page['access_token']
            account.save()
            connected.append(page['name'])

        if connected:
            messages.success(request, f"Connected: {', '.join(connected)}")
        else:
            messages.warning(request, "No pages were connected.")

    except requests.RequestException as e:
        messages.error(request, f"Network error: {e}")

    return redirect('post_list')