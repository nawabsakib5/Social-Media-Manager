import requests
import base64
import urllib.parse
from urllib.parse import urlencode
from django.conf import settings
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from .models import SocialAccount
from .utils import generate_pkce_pair
from integrations.facebook_adapter import FacebookAdapter


FB_APP_ID       = getattr(settings, 'FACEBOOK_APP_ID', '')
FB_APP_SECRET   = getattr(settings, 'FACEBOOK_APP_SECRET', '')
FB_REDIRECT_URI = getattr(settings, 'FACEBOOK_REDIRECT_URI', 'http://localhost:8000/posts/accounts/callback/')

TWITTER_CLIENT_ID = getattr(settings, 'TWITTER_CLIENT_ID', '')
TWITTER_CLIENT_SECRET = getattr(settings, 'TWITTER_CLIENT_SECRET', '')
TWITTER_REDIRECT_URI = f"{settings.SITE_URL}/posts/accounts/twitter/callback/"

LINKEDIN_CLIENT_ID = getattr(settings, 'LINKEDIN_CLIENT_ID', '')
LINKEDIN_CLIENT_SECRET = getattr(settings, 'LINKEDIN_CLIENT_SECRET', '')
LINKEDIN_REDIRECT_URI = getattr(settings, 'LINKEDIN_REDIRECT_URI', 'http://localhost:8000/posts/accounts/linkedin/callback/')


@login_required
def account_list(request):
    
    PLATFORMS = [
        'facebook', 'instagram', 'twitter', 'threads',
        'youtube', 'tiktok', 'whatsapp', 'linkedin', 'gmail',
    ]
    
    if request.user.is_superuser or getattr(request.user, 'user_type', None) == 'admin':
        user_accounts = SocialAccount.objects.all()
    else:
        user_accounts = SocialAccount.objects.filter(permitted_users=request.user)
        
    connected = {acc.platform: acc for acc in user_accounts}
    platform_data = [{'name': p, 'account': connected.get(p)} for p in PLATFORMS]
    
    return render(request, 'social_accounts/account_list.html', {
        'accounts': user_accounts.order_by('platform'),
        'platform_data': platform_data,
        'total_connected': user_accounts.count(),
    })


@login_required
def workspace(request, account_id=None):
    
    accounts = SocialAccount.objects.filter(connected_by=request.user, status='connected')
    
    if not accounts.exists():
        messages.warning(request, "Please connect a social media account first.")
        return redirect('social_accounts:account_list')
    
    if account_id:
        try:
            current_account = accounts.get(id=account_id)
        except SocialAccount.DoesNotExist:
            messages.error(request, "Account not found.")
            return redirect('social_accounts:workspace')
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
        context['error'] = f"{current_account.platform.capitalize()} workspace not implemented yet."
        template = 'social_accounts/workspace_base.html'
    
    return render(request, template, context)


def get_facebook_workspace_data(account):
    """Fetch Facebook page data with proper page token"""
    data = {'posts': [], 'conversations': [], 'error': None}
    
    try:
        adapter = FacebookAdapter()
        page_token, error = adapter.get_page_token(account)
        
        if error:
            data['error'] = error
            return data
        
        page_id = account.platform_account_id
        url = f"https://graph.facebook.com/v22.0/{page_id}/feed"
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
    """Reply to a comment on Facebook or Instagram."""
    if request.method != 'POST':
        return redirect('social_accounts:account_list')
    
    message = request.POST.get('message', '').strip()
    if not message:
        messages.error(request, "Reply cannot be empty.")
        return redirect('social_accounts:workspace')
    
    try:
        account = SocialAccount.objects.get(
            platform=platform, 
            status='connected', 
            connected_by=request.user
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
    """Reply to a Facebook Messenger conversation."""
    if request.method != 'POST':
        return redirect('social_accounts:account_list')
    
    recipient_id = request.POST.get('recipient_id', '').strip()
    message = request.POST.get('message', '').strip()
    
    if not message or not recipient_id:
        messages.error(request, "Message and recipient are required.")
        return redirect('social_accounts:workspace', platform='facebook')
    
    try:
        account = SocialAccount.objects.get(
            platform='facebook', 
            status='connected', 
            connected_by=request.user
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
    
    scopes = [
        'pages_show_list', 
        'pages_read_engagement',
        'pages_manage_posts', 
        'business_management',
        'instagram_basic', 
        'instagram_content_publish',
        'instagram_manage_comments', 
    ]
    
    params = {
        'client_id': FB_APP_ID,
        'redirect_uri': FB_REDIRECT_URI,
        'scope': ','.join(scopes),
        'response_type': 'code',
        'state': str(request.user.id),
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
    
    if state != str(request.user.id):
        messages.error(request, "Security check failed. Please try again.")
        return redirect('social_accounts:account_list')
    
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
            params={
                'access_token': long_token,
                'limit': 100
            },
            timeout=15
        ).json()
        
        if 'data' not in pages_data:
            messages.error(request, "No Facebook Pages found. Please create a page first.")
            return redirect('social_accounts:account_list')
        
        if not pages_data['data']:
            messages.warning(request, "No pages found to connect.")
            return redirect('social_accounts:account_list')
        
        connected_pages = []
        for page in pages_data['data']:
            page_id = page['id']
            page_name = page['name']
            
            page_token = page.get('access_token')
            
            if not page_token:
                page_token = long_token 

            account, created = SocialAccount.objects.update_or_create(
                platform='facebook',
                platform_account_id=page_id,
                defaults={
                    'account_name': page_name,
                    'status': 'connected',
                    'connected_by': request.user,
                }
            )
            
            account.access_token = page_token
            account.save()
            
            connected_pages.append(page_name)
            
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
                ig_id = ig_data['id']
                ig_username = ig_data.get('username', page_name)
                ig_name = ig_data.get('name', f"{page_name} (Instagram)")
                
                ig_account, _ = SocialAccount.objects.update_or_create(
                    platform='instagram',
                    platform_account_id=ig_id,
                    defaults={
                        'account_name': ig_name,
                        'account_username': ig_username,
                        'status': 'connected',
                        'connected_by': request.user,
                    }
                )
                
                ig_account.access_token = page_token
                ig_account.save()
                
                connected_pages.append(f"📸 {ig_username} (Instagram)")
        
        if connected_pages:
            messages.success(request, f"Successfully connected: {', '.join(connected_pages)}")
        else:
            messages.warning(request, "No pages were connected.")
            
    except requests.RequestException as e:
        messages.error(request, f"Network error during authentication: {str(e)}")
    
    return redirect('social_accounts:account_list')


@login_required
def disconnect_account(request, account_id):
    """Disconnect a social account"""
    if request.method != 'POST':
        return redirect('social_accounts:account_list')
    
    try:
        account = SocialAccount.objects.get(id=account_id, connected_by=request.user)
        account.status = 'disconnected'
        account.save()
        messages.success(request, f"{account.account_name} disconnected successfully.")
    except SocialAccount.DoesNotExist:
        messages.error(request, "Account not found.")
    
    return redirect('social_accounts:account_list')


@login_required
def twitter_login(request):
    """Initiate Twitter OAuth 2.0 flow with PKCE secure handshake"""
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
    """Handle Twitter OAuth 2.0 PKCE callback and register the Twitter Handle"""
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
        
    token_url = "https://api.twitter.com/2/oauth2/token"
    
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
        res = requests.post(token_url, headers=headers, data=payload, timeout=15)
        token_data = res.json()
        
        if 'access_token' not in token_data:
            error_desc = token_data.get('error_description', 'Token exchange failed.')
            messages.error(request, f"Twitter token error: {error_desc}")
            return redirect('social_accounts:account_list')
            
        access_token = token_data['access_token']
        refresh_token = token_data.get('refresh_token', '') 
        
        user_info_url = "https://api.twitter.com/2/users/me?user.fields=profile_image_url"
        user_headers = {'Authorization': f"Bearer {access_token}"}
        user_res = requests.get(user_info_url, headers=user_headers, timeout=10).json()
        user_data = user_res.get('data', {})
        
        if not user_data:
            messages.error(request, "Could not retrieve Twitter profile info.")
            return redirect('social_accounts:account_list')
            
        twitter_id = user_data.get('id')
        twitter_name = user_data.get('name', 'Twitter Account')
        twitter_username = user_data.get('username', '')
        profile_img = user_data.get('profile_image_url', '')
        
        sa, created = SocialAccount.objects.update_or_create(
            platform='twitter',
            platform_account_id=twitter_id,
            defaults={
                'account_name': twitter_name,
                'account_username': twitter_username,
                'profile_picture_url': profile_img,
                'status': 'connected',
                'connected_by': request.user,
            }
        )
        
        sa.access_token = access_token
        if refresh_token:
            sa.refresh_token = refresh_token
        sa.save()
        
        if not (request.user.is_superuser or getattr(request.user, 'user_type', None) == 'admin'):
            sa.permitted_users.add(request.user)
            
        messages.success(request, f"Successfully connected Twitter Account: @{twitter_username}")
        
    except requests.RequestException as e:
        messages.error(request, f"Network error during Twitter connection: {str(e)}")
        
    return redirect('social_accounts:account_list')




@login_required
def linkedin_login(request):
    """Initiate LinkedIn OAuth 2.0 flow using OpenID Connect scopes"""
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
    """Handle LinkedIn OAuth 2.0 callback, retrieve profile info and save connection"""
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
        
    token_url = "https://www.linkedin.com/oauth/v2/accessToken"
    payload = {
        'grant_type': 'authorization_code',
        'code': code,
        'redirect_uri': LINKEDIN_REDIRECT_URI,
        'client_id': LINKEDIN_CLIENT_ID,
        'client_secret': LINKEDIN_CLIENT_SECRET,
    }
    
    headers = {'Content-Type': 'application/x-www-form-urlencoded'}
    
    try:
        
        res = requests.post(token_url, headers=headers, data=payload, timeout=15)
        token_data = res.json()
        
        if 'access_token' not in token_data:
            err_msg = token_data.get('error_description', 'Token exchange failed.')
            messages.error(request, f"LinkedIn token error: {err_msg}")
            return redirect('social_accounts:account_list')
            
        access_token = token_data['access_token']
        
        
        user_info_url = "https://api.linkedin.com/v2/userinfo"
        user_headers = {'Authorization': f'Bearer {access_token}'}
        user_res = requests.get(user_info_url, headers=user_headers, timeout=10).json()
        
        
        linkedin_id = user_res.get('sub') 
        first_name = user_res.get('given_name', '')
        last_name = user_res.get('family_name', '')
        full_name = user_res.get('name', f"{first_name} {last_name}".strip() or 'LinkedIn User')
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
            }
        )
        
        
        sa.access_token = access_token
        sa.save()
        
        
        if not (request.user.is_superuser or getattr(request.user, 'user_type', None) == 'admin'):
            sa.permitted_users.add(request.user)
            
        messages.success(request, f"Successfully connected LinkedIn Profile: {full_name}")
        
    except requests.RequestException as e:
        messages.error(request, f"Network error during LinkedIn connection: {str(e)}")
        
    return redirect('social_accounts:account_list')