import requests
import base64
import urllib.parse
import secrets
from urllib.parse import urlencode
from django.conf import settings
from django.shortcuts import render, redirect, get_object_or_404
from django.db.models import Q
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from .models import SocialAccount
from .utils import generate_pkce_pair
from integrations.facebook_adapter import FacebookAdapter
from organizations.utils import get_user_organization

FB_APP_ID       = getattr(settings, 'FACEBOOK_APP_ID', '')
FB_APP_SECRET   = getattr(settings, 'FACEBOOK_APP_SECRET', '')
FB_REDIRECT_URI = getattr(settings, 'FACEBOOK_REDIRECT_URI', 'http://localhost:8000/posts/accounts/callback/')

TWITTER_CLIENT_ID = getattr(settings, 'TWITTER_CLIENT_ID', '')
TWITTER_CLIENT_SECRET = getattr(settings, 'TWITTER_CLIENT_SECRET', '')
TWITTER_REDIRECT_URI = f"{settings.SITE_URL}/posts/accounts/twitter/callback/"

LINKEDIN_CLIENT_ID = getattr(settings, 'LINKEDIN_CLIENT_ID', '')
LINKEDIN_CLIENT_SECRET = getattr(settings, 'LINKEDIN_CLIENT_SECRET', '')
LINKEDIN_REDIRECT_URI = getattr(settings, 'LINKEDIN_REDIRECT_URI', 'http://localhost:8000/posts/accounts/linkedin/callback/')

YOUTUBE_CLIENT_ID = getattr(settings, 'YOUTUBE_CLIENT_ID', '')
YOUTUBE_CLIENT_SECRET = getattr(settings, 'YOUTUBE_CLIENT_SECRET', '')
YOUTUBE_REDIRECT_URI = 'http://localhost:8000/posts/accounts/youtube/callback/'


def get_org_accounts(user):
    """শুধু user-এর Organization-এর accounts — অন্য Organization-এর
    accounts কোনোভাবেই আসবে না।"""
    org = get_user_organization(user)
    if not org:
        return SocialAccount.objects.none()
    is_admin_user = user.is_superuser or getattr(user, 'user_type', None) == 'admin'
    if is_admin_user:
        return SocialAccount.objects.filter(organization=org)
    return SocialAccount.objects.filter(organization=org, permitted_users=user)


@login_required
def account_list(request):
    PLATFORMS = [
        'facebook', 'instagram', 'twitter', 'linkedin',
        'telegram', 'pinterest', 'reddit', 'snapchat',
        'discord', 'threads', 'youtube',
        'tiktok', 'whatsapp', 'gmail',
    ]

    user_accounts = get_org_accounts(request.user)
    connected = {acc.platform: acc for acc in user_accounts}
    platform_data = [{'name': p, 'account': connected.get(p)} for p in PLATFORMS]

    return render(request, 'social_accounts/account_list.html', {
        'accounts': user_accounts.order_by('platform'),
        'platform_data': platform_data,
        'total_connected': user_accounts.count(),
    })


@login_required
def workspace(request, account_id=None):
    accounts = get_org_accounts(request.user).filter(status='connected')

    if not accounts.exists():
        messages.warning(request, "Please connect a social media account first.")
        return redirect('social_accounts:account_list')

    if account_id:
        try:
            current_account = accounts.get(id=account_id)
        except SocialAccount.DoesNotExist:
            messages.error(request, "Account not found.")
            return redirect('social_accounts:account_list')
    else:
        current_account = accounts.first()

    context = {
        'connected_accounts': accounts,
        'current_account': current_account,
        'platform': current_account.platform,
        'all_platform_accounts': accounts.filter(platform=current_account.platform),
    }

    if current_account.platform == 'facebook':
        context.update(get_facebook_workspace_data(current_account))
        template = 'social_accounts/workspace_facebook.html'
    elif current_account.platform == 'instagram':
        context.update(get_instagram_workspace_data(current_account))
        template = 'social_accounts/workspace_instagram.html'
    else:
        messages.info(request, f"{current_account.get_platform_display_name()} workspace will be available in the upcoming version!")
        return redirect('social_accounts:account_list')

    return render(request, template, context)


def get_facebook_workspace_data(account):
    data = {'posts': [], 'conversations': [], 'error': None}
    try:
        adapter = FacebookAdapter()
        page_token, error = adapter.get_page_token(account)
        if error:
            data['error'] = error
            return data

        page_id = account.platform_account_id
        url = f"https://graph.facebook.com/v22.0/{page_id}/published_posts"
        params = {
            'access_token': page_token,
            'fields': 'id,message,created_time,full_picture,'
                     'likes.summary(true),'
                     'comments{id,message,from,created_time},'
                     'shares,permalink_url',
            'limit': 20
        }

        response = requests.get(url, params=params, timeout=15)
        if response.status_code == 200:
            data['posts'] = response.json().get('data', [])
        else:
            data['error'] = f"Failed to fetch posts: {response.text}"
            return data

        conv_url = f"https://graph.facebook.com/v22.0/{page_id}/conversations"
        conv_params = {
            'access_token': page_token,
            'fields': 'participants,messages{message,from,created_time}',
            'limit': 10,
        }
        conv_response = requests.get(conv_url, params=conv_params, timeout=15)
        if conv_response.status_code == 200:
            data['conversations'] = conv_response.json().get('data', [])

        data['page_info'] = {
            'name': account.account_name,
            'id': page_id,
            'platform': 'facebook',
            'page_token': page_token[:20] + '...'
        }
    except requests.RequestException as e:
        data['error'] = f"Network error: {str(e)}"
    return data


def get_instagram_workspace_data(account):
    data = {'posts': [], 'error': None, 'page_info': {}}
    try:
        adapter = FacebookAdapter()
        page_token, error = adapter.get_page_token(account)
        if error:
            data['error'] = error
            return data

        page_id = account.platform_account_id
        url = f"https://graph.facebook.com/v22.0/{page_id}"
        params = {
            'access_token': page_token,
            'fields': 'instagram_business_account{id,username,profile_picture_url}'
        }
        response = requests.get(url, params=params, timeout=15)
        if response.status_code != 200:
            data['error'] = f"Failed to get Instagram ID: {response.text}"
            return data

        ig_data = response.json().get('instagram_business_account', {})
        ig_id = ig_data.get('id')
        if not ig_id:
            data['error'] = 'No Instagram Business Account connected to this page'
            return data

        media_url = f"https://graph.facebook.com/v22.0/{ig_id}/media"
        media_params = {
            'access_token': page_token,
            'fields': 'id,caption,media_type,media_url,thumbnail_url,timestamp,'
                     'like_count,comments_count,'
                     'comments{id,text,username,timestamp}',
            'limit': 20
        }
        media_response = requests.get(media_url, params=media_params, timeout=15)
        if media_response.status_code == 200:
            data['posts'] = media_response.json().get('data', [])
        else:
            data['error'] = f"Failed to fetch Instagram posts: {media_response.text}"
            return data

        data['page_info'] = {
            'name': account.account_name,
            'id': page_id,
            'instagram_id': ig_id,
            'instagram_username': ig_data.get('username', ''),
            'platform': 'instagram',
        }
    except requests.RequestException as e:
        data['error'] = f"Network error: {str(e)}"
    return data


@login_required
def post_comment_reply(request, platform, comment_id):
    if request.method != 'POST':
        return redirect('social_accounts:account_list')

    message = request.POST.get('message', '').strip()
    if not message:
        messages.error(request, "Reply cannot be empty.")
        return redirect('social_accounts:workspace')

    org = get_user_organization(request.user)
    is_admin_user = request.user.is_superuser or getattr(request.user, 'user_type', None) == 'admin'

    try:
        if is_admin_user:
            account = SocialAccount.objects.get(organization=org, platform=platform, status='connected')
        else:
            account = SocialAccount.objects.get(
                Q(connected_by=request.user) | Q(permitted_users=request.user),
                organization=org, platform=platform, status='connected',
            )
    except SocialAccount.DoesNotExist:
        messages.error(request, f"{platform.capitalize()} account not connected.")
        return redirect('social_accounts:account_list')

    adapter = FacebookAdapter()
    page_token, error = adapter.get_page_token(account)
    if error:
        messages.error(request, f"Failed to get page token: {error}")
        return redirect('social_accounts:workspace')

    base = "https://graph.facebook.com/v22.0"
    try:
        if platform == 'facebook':
            res = requests.post(
                f"{base}/{comment_id}/comments",
                data={'message': message, 'access_token': page_token},
                timeout=15
            ).json()
        elif platform == 'instagram':
            res = requests.post(
                f"{base}/{comment_id}/replies",
                data={'message': message, 'access_token': page_token},
                timeout=15
            ).json()
        else:
            messages.error(request, 'Platform not supported for replies')
            return redirect('social_accounts:workspace')

        if 'error' in res:
            messages.error(request, res['error'].get('message', 'Reply failed.'))
        else:
            messages.success(request, "Reply posted successfully.")
    except requests.RequestException as e:
        messages.error(request, f"Network error: {str(e)}")

    return redirect('social_accounts:workspace')


@login_required
def send_messenger_reply(request):
    if request.method != 'POST':
        return redirect('social_accounts:account_list')

    recipient_id = request.POST.get('recipient_id', '').strip()
    message = request.POST.get('message', '').strip()

    if not message or not recipient_id:
        messages.error(request, "Message and recipient are required.")
        return redirect('social_accounts:workspace')

    org = get_user_organization(request.user)
    is_admin_user = request.user.is_superuser or getattr(request.user, 'user_type', None) == 'admin'

    try:
        if is_admin_user:
            account = SocialAccount.objects.get(organization=org, platform='facebook', status='connected')
        else:
            account = SocialAccount.objects.get(
                Q(connected_by=request.user) | Q(permitted_users=request.user),
                organization=org, platform='facebook', status='connected',
            )
    except SocialAccount.DoesNotExist:
        messages.error(request, "Facebook account not connected.")
        return redirect('social_accounts:account_list')

    adapter = FacebookAdapter()
    page_token, error = adapter.get_page_token(account)
    if error:
        messages.error(request, f"Failed to get page token: {error}")
        return redirect('social_accounts:workspace')

    try:
        base = "https://graph.facebook.com/v22.0"
        res = requests.post(
            f"{base}/me/messages",
            params={'access_token': page_token},
            json={
                'recipient': {'id': recipient_id},
                'message': {'text': message},
            },
            timeout=15
        ).json()

        if 'error' in res:
            messages.error(request, res['error'].get('message', 'Message failed.'))
        else:
            messages.success(request, "Message sent successfully.")
    except requests.RequestException as e:
        messages.error(request, f"Network error: {str(e)}")

    return redirect('social_accounts:workspace')


@login_required
def facebook_login(request):
    state = secrets.token_urlsafe(32)
    request.session['fb_oauth_state'] = state
    request.session['fb_oauth_user_id'] = request.user.id

    scopes = [
        'pages_show_list',
        'pages_read_engagement',
        'pages_manage_posts',
        'pages_manage_engagement',
        'business_management',
        'instagram_basic',
        'instagram_content_publish',
        'instagram_manage_comments',
        'instagram_manage_messages',
        'pages_read_user_content',
        'pages_messaging',
    ]

    params = {
        'client_id': FB_APP_ID,
        'redirect_uri': FB_REDIRECT_URI,
        'scope': ','.join(scopes),
        'response_type': 'code',
        'state': state,
        'auth_type': 'rerequest',
    }

    return redirect(f"https://www.facebook.com/v22.0/dialog/oauth?{urlencode(params)}")


@login_required
def facebook_callback(request):
    code = request.GET.get('code')
    state = request.GET.get('state')
    error = request.GET.get('error')
    error_reason = request.GET.get('error_reason', '')
    error_description = request.GET.get('error_description', '')

    if error or not code:
        error_msg = error_description or error_reason or error or 'No code received.'
        messages.error(request, f"Facebook login failed: {error_msg}")
        return redirect('social_accounts:account_list')

    session_state = request.session.get('fb_oauth_state')
    if session_state and state != session_state:
        messages.error(request, "Security check failed. Please try again.")
        return redirect('social_accounts:account_list')

    request.session.pop('fb_oauth_state', None)
    request.session.pop('fb_oauth_user_id', None)

    try:
        token_res = requests.get(
            "https://graph.facebook.com/v22.0/oauth/access_token",
            params={
                'client_id': FB_APP_ID,
                'redirect_uri': FB_REDIRECT_URI,
                'client_secret': FB_APP_SECRET,
                'code': code,
            },
            timeout=15
        ).json()

        if 'access_token' not in token_res:
            error_msg = token_res.get('error', {}).get('message', 'Token exchange failed.')
            messages.error(request, f"Token exchange failed: {error_msg}")
            return redirect('social_accounts:account_list')

        short_token = token_res['access_token']

        long_res = requests.get(
            "https://graph.facebook.com/v22.0/oauth/access_token",
            params={
                'grant_type': 'fb_exchange_token',
                'client_id': FB_APP_ID,
                'client_secret': FB_APP_SECRET,
                'fb_exchange_token': short_token,
            },
            timeout=15
        ).json()

        long_token = long_res.get('access_token', short_token)

        pages_data = requests.get(
            "https://graph.facebook.com/v22.0/me/accounts",
            params={'access_token': long_token, 'limit': 100},
            timeout=15
        ).json()

        if 'data' not in pages_data or not pages_data['data']:
            messages.warning(request, "No Facebook Pages found.")
            return redirect('social_accounts:account_list')

        # ── page-selection flow ──
        # সব page-এর তথ্য + linked Instagram session-এ রেখে
        # client-কে select করতে পাঠানো হচ্ছে
        page_choices = []
        for page in pages_data['data']:
            page_id = page['id']
            page_name = page['name']
            page_token = page.get('access_token', long_token)

            ig_info = None
            try:
                instagram_check = requests.get(
                    f"https://graph.facebook.com/v22.0/{page_id}",
                    params={
                        'access_token': page_token,
                        'fields': 'instagram_business_account{id,username,name}'
                    },
                    timeout=10
                ).json()
                ig_data = instagram_check.get('instagram_business_account')
                if ig_data and ig_data.get('id'):
                    ig_info = {
                        'id': ig_data['id'],
                        'username': ig_data.get('username', page_name),
                        'name': ig_data.get('name', f"{page_name} (Instagram)"),
                    }
            except requests.RequestException:
                ig_info = None

            page_choices.append({
                'page_id': page_id,
                'page_name': page_name,
                'access_token': page_token,
                'instagram': ig_info,
            })

        request.session['fb_pending_pages'] = page_choices
        return redirect('social_accounts:facebook_select_pages')

    except requests.RequestException as e:
        messages.error(request, f"Network error during authentication: {str(e)}")

    return redirect('social_accounts:account_list')


@login_required
def facebook_select_pages(request):
    """Client নিজে বেছে নেবে কোন Facebook Page আর Instagram connect করবে।
    কোথাও password চাওয়া হচ্ছে না — পুরোটাই OAuth token-ভিত্তিক।"""
    pages = request.session.get('fb_pending_pages')
    if not pages:
        messages.error(request, "No pending pages found. Please reconnect.")
        return redirect('social_accounts:account_list')
    return render(request, 'social_accounts/select_pages.html', {'pages': pages})


@login_required
def facebook_connect_selected_pages(request):
    """শুধু client-এর check করা page গুলোই connect হবে।"""
    if request.method != 'POST':
        return redirect('social_accounts:account_list')

    pages = request.session.get('fb_pending_pages')
    if not pages:
        messages.error(request, "Session expired. Please reconnect.")
        return redirect('social_accounts:account_list')

    selected_ids = set(request.POST.getlist('page_ids'))
    is_admin_user = request.user.is_superuser or getattr(request.user, 'user_type', None) == 'admin'
    org = get_user_organization(request.user)
    connected_pages = []

    for page in pages:
        if page['page_id'] not in selected_ids:
            continue

        account, _ = SocialAccount.objects.update_or_create(
            platform='facebook',
            platform_account_id=page['page_id'],
            defaults={
                'account_name': page['page_name'],
                'status': 'connected',
                'connected_by': request.user,
                'organization': org,
            }
        )
        account.access_token = page['access_token']
        account.save()
        if not is_admin_user:
            account.permitted_users.add(request.user)
        connected_pages.append(page['page_name'])

        ig = page.get('instagram')
        if ig:
            ig_account, _ = SocialAccount.objects.update_or_create(
                platform='instagram',
                platform_account_id=ig['id'],
                defaults={
                    'account_name': ig.get('name') or page['page_name'],
                    'account_username': ig.get('username', page['page_name']),
                    'status': 'connected',
                    'connected_by': request.user,
                    'organization': org,
                }
            )
            ig_account.access_token = page['access_token']
            ig_account.save()
            if not is_admin_user:
                ig_account.permitted_users.add(request.user)
            connected_pages.append(f"📸 {ig.get('username')} (Instagram)")

    request.session.pop('fb_pending_pages', None)

    if connected_pages:
        messages.success(request, f"Successfully connected: {', '.join(connected_pages)}")
    else:
        messages.warning(request, "No pages were selected.")

    return redirect('social_accounts:account_list')


@login_required
def disconnect_account(request, account_id):
    if request.method != 'POST':
        return redirect('social_accounts:account_list')

    org = get_user_organization(request.user)
    is_admin_user = request.user.is_superuser or getattr(request.user, 'user_type', None) == 'admin'

    try:
        if is_admin_user:
            account = SocialAccount.objects.get(id=account_id, organization=org)
        else:
            account = SocialAccount.objects.get(id=account_id, connected_by=request.user, organization=org)

        account.status = 'disconnected'
        account.save()
        messages.success(request, f"{account.account_name} disconnected successfully.")
    except SocialAccount.DoesNotExist:
        messages.error(request, "Account not found or permission denied.")

    return redirect('social_accounts:account_list')


@login_required
def twitter_login(request):
    verifier, challenge = generate_pkce_pair()
    request.session['twitter_code_verifier'] = verifier

    params = {
        'response_type': 'code',
        'client_id': TWITTER_CLIENT_ID,
        'redirect_uri': TWITTER_REDIRECT_URI,
        'scope': 'tweet.read tweet.write users.read offline.access',
        'state': str(request.user.id),
        'code_challenge': challenge,
        'code_challenge_method': 'S256',
    }

    auth_url = "https://twitter.com/i/oauth2/authorize?" + urllib.parse.urlencode(params)
    return redirect(auth_url)


@login_required
def twitter_callback(request):
    code = request.GET.get('code')
    state = request.GET.get('state')
    error = request.GET.get('error')

    if error or not code:
        messages.error(request, f"Twitter connection failed: {error or 'No code received.'}")
        return redirect('social_accounts:account_list')

    if state != str(request.user.id):
        messages.error(request, "Security check failed. Please try again.")
        return redirect('social_accounts:account_list')

    verifier = request.session.get('twitter_code_verifier')
    if not verifier:
        messages.error(request, "Session expired. Please try connecting again.")
        return redirect('social_accounts:account_list')

    auth_str = f"{TWITTER_CLIENT_ID}:{TWITTER_CLIENT_SECRET}"
    b64_auth = base64.b64encode(auth_str.encode('utf-8')).decode('utf-8')

    headers = {
        'Authorization': f'Basic {b64_auth}',
        'Content-Type': 'application/x-www-form-urlencoded',
    }

    payload = {
        'code': code,
        'grant_type': 'authorization_code',
        'redirect_uri': TWITTER_REDIRECT_URI,
        'code_verifier': verifier,
    }

    try:
        res = requests.post("https://api.twitter.com/2/oauth2/token", headers=headers, data=payload, timeout=15)
        token_data = res.json()

        if 'access_token' not in token_data:
            messages.error(request, f"Twitter token error: {token_data.get('error_description', 'Token exchange failed.')}")
            return redirect('social_accounts:account_list')

        access_token = token_data['access_token']
        refresh_token = token_data.get('refresh_token', '')

        user_res = requests.get(
            "https://api.twitter.com/2/users/me?user.fields=profile_image_url",
            headers={'Authorization': f"Bearer {access_token}"},
            timeout=10
        ).json()
        user_data = user_res.get('data', {})

        if not user_data:
            messages.error(request, "Could not retrieve Twitter profile info.")
            return redirect('social_accounts:account_list')

        sa, created = SocialAccount.objects.update_or_create(
            platform='twitter',
            platform_account_id=user_data.get('id'),
            defaults={
                'account_name': user_data.get('name', 'Twitter Account'),
                'account_username': user_data.get('username', ''),
                'profile_picture_url': user_data.get('profile_image_url', ''),
                'status': 'connected',
                'connected_by': request.user,
                'organization': get_user_organization(request.user),
            }
        )
        sa.access_token = access_token
        if refresh_token:
            sa.refresh_token = refresh_token
        sa.save()

        if not (request.user.is_superuser or getattr(request.user, 'user_type', None) == 'admin'):
            sa.permitted_users.add(request.user)

        messages.success(request, f"Successfully connected Twitter: @{user_data.get('username', '')}")

    except requests.RequestException as e:
        messages.error(request, f"Network error during Twitter connection: {str(e)}")

    return redirect('social_accounts:account_list')


@login_required
def linkedin_login(request):
    params = {
        'response_type': 'code',
        'client_id': LINKEDIN_CLIENT_ID,
        'redirect_uri': LINKEDIN_REDIRECT_URI,
        'state': str(request.user.id),
        'scope': 'openid profile email w_member_social',
    }
    auth_url = "https://www.linkedin.com/oauth/v2/authorization?" + urllib.parse.urlencode(params)
    return redirect(auth_url)


@login_required
def linkedin_callback(request):
    code = request.GET.get('code')
    state = request.GET.get('state')
    error = request.GET.get('error')
    error_desc = request.GET.get('error_description', '')

    if error or not code:
        messages.error(request, f"LinkedIn connection failed: {error_desc or error or 'No code received.'}")
        return redirect('social_accounts:account_list')

    if state != str(request.user.id):
        messages.error(request, "Security check failed. Please try again.")
        return redirect('social_accounts:account_list')

    payload = {
        'grant_type': 'authorization_code',
        'code': code,
        'redirect_uri': LINKEDIN_REDIRECT_URI,
        'client_id': LINKEDIN_CLIENT_ID,
        'client_secret': LINKEDIN_CLIENT_SECRET,
    }

    try:
        res = requests.post(
            "https://www.linkedin.com/oauth/v2/accessToken",
            headers={'Content-Type': 'application/x-www-form-urlencoded'},
            data=payload,
            timeout=15
        )
        token_data = res.json()

        if 'access_token' not in token_data:
            messages.error(request, f"LinkedIn token error: {token_data.get('error_description', 'Token exchange failed.')}")
            return redirect('social_accounts:account_list')

        access_token = token_data['access_token']

        user_res = requests.get(
            "https://api.linkedin.com/v2/userinfo",
            headers={'Authorization': f'Bearer {access_token}'},
            timeout=10
        ).json()

        linkedin_id = user_res.get('sub')
        full_name = user_res.get('name', f"{user_res.get('given_name', '')} {user_res.get('family_name', '')}".strip() or 'LinkedIn User')
        profile_img = user_res.get('picture', '')

        if not linkedin_id:
            messages.error(request, "Could not retrieve LinkedIn profile details.")
            return redirect('social_accounts:account_list')

        sa, created = SocialAccount.objects.update_or_create(
            platform='linkedin',
            platform_account_id=linkedin_id,
            defaults={
                'account_name': full_name,
                'profile_picture_url': profile_img,
                'status': 'connected',
                'connected_by': request.user,
                'organization': get_user_organization(request.user),
            }
        )
        sa.access_token = access_token
        sa.save()

        if not (request.user.is_superuser or getattr(request.user, 'user_type', None) == 'admin'):
            sa.permitted_users.add(request.user)

        messages.success(request, f"Successfully connected LinkedIn: {full_name}")

    except requests.RequestException as e:
        messages.error(request, f"Network error during LinkedIn connection: {str(e)}")

    return redirect('social_accounts:account_list')


@login_required
def youtube_login(request):
    params = {
        'client_id': YOUTUBE_CLIENT_ID,
        'redirect_uri': YOUTUBE_REDIRECT_URI,
        'response_type': 'code',
        'scope': ' '.join([
            'https://www.googleapis.com/auth/youtube',
            'https://www.googleapis.com/auth/youtube.upload',
            'https://www.googleapis.com/auth/youtube.force-ssl',
        ]),
        'access_type': 'offline',
        'prompt': 'consent',
        'state': str(request.user.id),
    }
    auth_url = "https://accounts.google.com/o/oauth2/v2/auth?" + urllib.parse.urlencode(params)
    return redirect(auth_url)


def youtube_callback(request):
    code = request.GET.get('code')
    state = request.GET.get('state')
    error = request.GET.get('error')

    if error or not code:
        messages.error(request, f"YouTube connection failed: {error or 'No code received.'}")
        return redirect('social_accounts:account_list')

    if not request.user.is_authenticated:
        from django.contrib.auth.views import redirect_to_login
        return redirect_to_login(request.get_full_path())

    if state != str(request.user.id):
        messages.error(request, "Security check failed. Please try again.")
        return redirect('social_accounts:account_list')

    try:
        token_res = requests.post(
            'https://oauth2.googleapis.com/token',
            data={
                'code': code,
                'client_id': YOUTUBE_CLIENT_ID,
                'client_secret': YOUTUBE_CLIENT_SECRET,
                'redirect_uri': YOUTUBE_REDIRECT_URI,
                'grant_type': 'authorization_code',
            },
            timeout=15
        ).json()

        if 'access_token' not in token_res:
            messages.error(request, f"YouTube token error: {token_res.get('error_description', 'Token exchange failed.')}")
            return redirect('social_accounts:account_list')

        access_token = token_res['access_token']
        refresh_token = token_res.get('refresh_token', '')

        channel_res = requests.get(
            'https://www.googleapis.com/youtube/v3/channels',
            headers={'Authorization': f'Bearer {access_token}'},
            params={'part': 'snippet', 'mine': 'true'},
            timeout=15
        ).json()

        items = channel_res.get('items', [])
        if not items:
            messages.error(request, "No YouTube channel found.")
            return redirect('social_accounts:account_list')

        channel = items[0]
        channel_id = channel['id']
        channel_title = channel['snippet']['title']
        profile_pic = channel['snippet']['thumbnails']['default']['url']

        sa, created = SocialAccount.objects.update_or_create(
            platform='youtube',
            platform_account_id=channel_id,
            defaults={
                'account_name': channel_title,
                'profile_picture_url': profile_pic,
                'status': 'connected',
                'connected_by': request.user,
                'organization': get_user_organization(request.user),
            }
        )
        sa.access_token = access_token
        if refresh_token:
            sa.refresh_token = refresh_token
        sa.save()

        if not (request.user.is_superuser or getattr(request.user, 'user_type', None) == 'admin'):
            sa.permitted_users.add(request.user)

        messages.success(request, f"Successfully connected YouTube: {channel_title}")

    except requests.RequestException as e:
        messages.error(request, f"Network error: {str(e)}")

    return redirect('social_accounts:account_list')