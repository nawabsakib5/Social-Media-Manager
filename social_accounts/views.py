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
    platform_data = [{'name': p, 'account': connected.get(p)} for p in PLATFORMS]
    return render(request, 'social_accounts/account_list.html', {
        'accounts': SocialAccount.objects.all().order_by('platform'),
        'platform_data': platform_data,
    })


@login_required
def workspace(request, platform):
    try:
        account = SocialAccount.objects.get(platform=platform, status='connected')
    except SocialAccount.DoesNotExist:
        messages.error(request, f"{platform.capitalize()} account not connected.")
        return redirect('social_accounts:account_list')

    context = {'account': account, 'platform': platform}

    if platform == 'facebook':
        context.update(_get_facebook_data(account))
    elif platform == 'instagram':
        context.update(_get_instagram_data(account))

    return render(request, f'social_accounts/workspace_{platform}.html', context)


def _get_facebook_data(account):
    token   = account.access_token
    page_id = account.platform_account_id
    base    = "https://graph.facebook.com/v21.0"
    
    # 'messages' কি-টি পরিবর্তন করে 'conversations' করা হয়েছে
    data    = {'posts': [], 'conversations': [], 'error': None}

    try:
        # Step 1: Get page access token from system user token
        accounts_res = requests.get(
            f"{base}/me/accounts",
            params={'access_token': token},
            timeout=15
        ).json()

        page_token = token  # fallback
        for page in accounts_res.get('data', []):
            if page.get('id') == page_id:
                page_token = page['access_token']
                break

        # Step 2: Fetch posts with page token
        posts_res = requests.get(
            f"{base}/{page_id}/posts",
            params={
                'access_token': page_token,
                'fields': 'id,message,created_time,full_picture,'
                          'likes.summary(true),'
                          'comments{id,message,from,created_time}',
                'limit': 10,
            },
            timeout=15
        ).json()

        if 'error' in posts_res:
            data['error'] = posts_res['error'].get('message', 'Facebook API error')
        else:
            data['posts'] = posts_res.get('data', [])

        # Step 3: Fetch conversations
        conv_res = requests.get(
            f"{base}/{page_id}/conversations",
            params={
                'access_token': page_token,
                'fields': 'participants,messages{message,from,created_time}',
                'limit': 10,
            },
            timeout=15
        ).json()
        
        # 'messages' থেকে পরিবর্তন করে 'conversations' কী-তে ডেটা এসাইন করা হয়েছে
        data['conversations'] = conv_res.get('data', [])

    except requests.RequestException as e:
        data['error'] = f"Network error: {e}"

    return data


def _get_instagram_data(account):
    """Fetch posts + comments for Instagram workspace."""
    token   = account.access_token
    ig_id   = account.platform_account_id
    base    = "https://graph.facebook.com/v21.0"
    data    = {'posts': [], 'error': None}

    try:
        posts_res = requests.get(
            f"{base}/{ig_id}/media",
            params={
                'access_token': token,
                'fields': 'id,caption,media_type,media_url,thumbnail_url,timestamp,like_count,comments_count,comments{id,text,username,timestamp}',
                'limit': 10,
            },
            timeout=15
        ).json()

        if 'error' in posts_res:
            data['error'] = posts_res['error'].get('message', 'Instagram API error')
        else:
            data['posts'] = posts_res.get('data', [])

    except requests.RequestException as e:
        data['error'] = f"Network error: {e}"

    return data


@login_required
def post_comment_reply(request, platform, comment_id):
    """Reply to a comment on Facebook or Instagram."""
    if request.method != 'POST':
        return redirect('social_accounts:account_list')

    message = request.POST.get('message', '').strip()
    if not message:
        messages.error(request, "Reply cannot be empty.")
        return redirect('social_accounts:workspace', platform=platform)

    try:
        account = SocialAccount.objects.get(platform=platform, status='connected')
    except SocialAccount.DoesNotExist:
        messages.error(request, "Account not connected.")
        return redirect('social_accounts:account_list')

    token = account.access_token
    base  = "https://graph.facebook.com/v21.0"

    try:
        if platform == 'facebook':
            res = requests.post(
                f"{base}/{comment_id}/comments",
                data={'message': message, 'access_token': token},
                timeout=15
            ).json()
        elif platform == 'instagram':
            res = requests.post(
                f"{base}/{comment_id}/replies",
                data={'message': message, 'access_token': token},
                timeout=15
            ).json()
        else:
            res = {'error': {'message': 'Platform not supported'}}

        if 'error' in res:
            messages.error(request, res['error'].get('message', 'Reply failed.'))
        else:
            messages.success(request, "Reply posted successfully.")

    except requests.RequestException as e:
        messages.error(request, f"Network error: {e}")

    return redirect('social_accounts:workspace', platform=platform)


@login_required
def send_messenger_reply(request):
    """Reply to a Facebook Messenger conversation."""
    if request.method != 'POST':
        return redirect('social_accounts:account_list')

    recipient_id = request.POST.get('recipient_id', '').strip()
    message      = request.POST.get('message', '').strip()

    if not message or not recipient_id:
        messages.error(request, "Message and recipient are required.")
        return redirect('social_accounts:workspace', platform='facebook')

    try:
        account = SocialAccount.objects.get(platform='facebook', status='connected')
    except SocialAccount.DoesNotExist:
        messages.error(request, "Facebook account not connected.")
        return redirect('social_accounts:account_list')

    token   = account.access_token
    page_id = account.platform_account_id
    base    = "https://graph.facebook.com/v21.0"

    try:
        res = requests.post(
            f"{base}/{page_id}/messages",
            params={'access_token': token},
            json={
                'recipient': {'id': recipient_id},
                'message':   {'text': message},
            },
            timeout=15
        ).json()

        if 'error' in res:
            messages.error(request, res['error'].get('message', 'Message failed.'))
        else:
            messages.success(request, "Message sent successfully.")

    except requests.RequestException as e:
        messages.error(request, f"Network error: {e}")

    return redirect('social_accounts:workspace', platform='facebook')


@login_required
def facebook_login(request):
    scopes = [
        'pages_show_list', 'pages_read_engagement',
        'pages_manage_posts', 'business_management',
        'instagram_basic', 'instagram_content_publish',
        'pages_messaging',
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
        messages.error(request, "Security check failed.")
        return redirect('post_list')

    try:
        token_res = requests.get(
            "https://graph.facebook.com/v21.0/oauth/access_token",
            params={
                'client_id': FB_APP_ID, 'redirect_uri': FB_REDIRECT_URI,
                'client_secret': FB_APP_SECRET, 'code': code,
            }, timeout=15
        ).json()

        if 'access_token' not in token_res:
            messages.error(request, token_res.get('error', {}).get('message', 'Token exchange failed.'))
            return redirect('post_list')

        short_token = token_res['access_token']
        long_res = requests.get(
            "https://graph.facebook.com/v21.0/oauth/access_token",
            params={
                'grant_type': 'fb_exchange_token', 'client_id': FB_APP_ID,
                'client_secret': FB_APP_SECRET, 'fb_exchange_token': short_token,
            }, timeout=15
        ).json()
        long_token = long_res.get('access_token', short_token)

        pages_data = requests.get(
            "https://graph.facebook.com/v21.0/me/accounts",
            params={'access_token': long_token}, timeout=15
        ).json()

        if 'data' not in pages_data:
            messages.error(request, "No Facebook Pages found.")
            return redirect('post_list')

        connected = []
        for page in pages_data['data']:
            account, _ = SocialAccount.objects.update_or_create(
                platform='facebook',
                platform_account_id=page['id'],
                defaults={
                    'account_name': page['name'],
                    'status': 'connected',
                    'connected_by': request.user,
                }
            )
            account.access_token = page['access_token']
            account.save()
            connected.append(page['name'])

        if connected:
            messages.success(request, f"Connected: {', '.join(connected)}")
        else:
            messages.warning(request, "No pages connected.")

    except requests.RequestException as e:
        messages.error(request, f"Network error: {e}")

    return redirect('post_list')