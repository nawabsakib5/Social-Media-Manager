# inbox/views.py (সম্পূর্ণ ফাইলটি কপি করে রিপ্লেস করে সেভ করে দিন)
import requests
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from social_accounts.models import SocialAccount
from integrations.facebook_adapter import FacebookAdapter
from .models import InboxItem, Reply

@login_required
def inbox_list(request):
    """Display the list of inbox comments and messages with dynamic filtering."""
    selected_platform = request.GET.get('platform', '')
    selected_type = request.GET.get('type', '')
    active_item_id = request.GET.get('item_id', '')
    
    # Fetch inbox items connected to the logged-in user's social accounts
    items = InboxItem.objects.filter(social_account__connected_by=request.user)
    
    if selected_platform:
        items = items.filter(social_account__platform=selected_platform)
    if selected_type:
        items = items.filter(type=selected_type)
        
    unread_count = items.filter(is_read=False).count()
    
    # Load the selected conversation in the right pane
    active_item = None
    if active_item_id:
        try:
            active_item = items.get(id=active_item_id)
            if not active_item.is_read:
                active_item.is_read = True
                active_item.save(update_fields=['is_read'])
        except InboxItem.DoesNotExist:
            pass
    elif items.exists():
        # Fallback to the first item if none is selected
        active_item = items.first()
        if active_item and not active_item.is_read:
            active_item.is_read = True
            active_item.save(update_fields=['is_read'])
            
    context = {
        'items': items.order_by('-received_at'),
        'selected_platform': selected_platform,
        'selected_type': selected_type,
        'unread_count': unread_count,
        'active_item': active_item,
    }
    return render(request, 'inbox/inbox_list.html', context)


@login_required
def sync_inbox_data(request):
    """Sync comments and messages directly from Facebook, Instagram, Twitter/X, and LinkedIn APIs with Failsafe handling."""
    connected_accounts = SocialAccount.objects.filter(connected_by=request.user, status='connected')
    
    if not connected_accounts.exists():
        messages.warning(request, "Please connect at least one social media account before syncing the inbox.")
        return redirect('inbox_list')
        
    synced_count = 0
    adapter = FacebookAdapter()
    
    for account in connected_accounts:
        page_token, error = adapter.get_page_token(account)
        if error:
            continue
            
        try:
            if account.platform == 'facebook':
                # ফেইল-সেফ হ্যান্ডলিং: একটি পেজে এরর থাকলেও অন্য পেজগুলোর কমেন্ট সফলভাবে সিঙ্ক হবে
                try:
                    synced_count += _sync_facebook_comments(account, page_token)
                except Exception as e:
                    print(f"[Inbox Sync Error] Facebook Comments sync failed for {account.account_name}: {e}")
                    
                try:
                    synced_count += _sync_facebook_messages(account, page_token)
                except Exception as e:
                    print(f"[Inbox Sync Error] Facebook Messenger sync failed for {account.account_name}: {e}")
                
            elif account.platform == 'instagram':
                try:
                    synced_count += _sync_instagram_comments(account, page_token)
                except Exception as e:
                    print(f"[Inbox Sync Error] Instagram Comments sync failed for {account.account_name}: {e}")
                    
            elif account.platform == 'twitter':
                try:
                    synced_count += _sync_twitter_mentions(account, page_token)
                except Exception as e:
                    print(f"[Inbox Sync Error] Twitter Mentions sync failed for {account.account_name}: {e}")
                    
            elif account.platform == 'linkedin':
                try:
                    synced_count += _sync_linkedin_comments(account, page_token)
                except Exception as e:
                    print(f"[Inbox Sync Error] LinkedIn Comments sync failed for {account.account_name}: {e}")
        except Exception as e:
            print(f"General Sync Exception for {account.account_name}: {e}")
            
    messages.success(request, f"Successfully synced {synced_count} new items to your inbox!")
    return redirect('inbox_list')


# inbox/views.py (এই _sync_facebook_comments ফাংশনটি পরিবর্তন করে সেভ করুন)
def _sync_facebook_comments(account, page_token):
    """Sync comments from the Facebook Page published_posts (Failsafe workaround for API v22.0)."""
    page_id = account.platform_account_id
    
    # মেটার নতুন pages_read_engagement রেস্ট্রিকশন এড়াতে /feed এর বদলে /published_posts ব্যবহার করা হয়েছে
    url = f"https://graph.facebook.com/v22.0/{page_id}/published_posts"
    params = {
        'access_token': page_token,
        'fields': 'id,comments{id,message,from,created_time}'
    }
    count = 0
    response = requests.get(url, params=params, timeout=15).json()
    
    if 'error' in response:
        print(f"[Meta API Exception] Page {account.account_name} returned error: {response['error'].get('message')}")
        return 0
        
    posts = response.get('data', [])
    for post in posts:
        comments = post.get('comments', {}).get('data', [])
        for comment in comments:
            # Ignore comments made by the Page itself
            if comment.get('from', {}).get('id') == page_id:
                continue
                
            created_time = parse_datetime(comment.get('created_time'))
            obj, created = InboxItem.objects.update_or_create(
                item_id=comment['id'],
                defaults={
                    'social_account': account,
                    'type': 'comment',
                    'sender_id': comment.get('from', {}).get('id'),
                    'sender_name': comment.get('from', {}).get('name', 'FB User'),
                    'content': comment.get('message', ''),
                    'received_at': created_time,
                }
            )
            if created:
                count += 1
    return count

def _sync_facebook_messages(account, page_token):
    """Sync direct messages from the Facebook Page inbox (Messenger)."""
    page_id = account.platform_account_id
    url = f"https://graph.facebook.com/v22.0/{page_id}/conversations"
    params = {
        'access_token': page_token,
        'fields': 'id,updated_time,messages{id,message,from,created_time}'
    }
    count = 0
    response = requests.get(url, params=params, timeout=15).json()
    
    if 'error' in response:
        print(f"[Meta API Exception] Page {account.account_name} Messenger returned error: {response['error'].get('message')}")
        return 0
        
    conversations = response.get('data', [])
    for conv in conversations:
        messages_list = conv.get('messages', {}).get('data', [])
        if messages_list:
            latest_msg = messages_list[0]
            if latest_msg.get('from', {}).get('id') == page_id:
                continue
                
            created_time = parse_datetime(latest_msg.get('created_time'))
            obj, created = InboxItem.objects.update_or_create(
                item_id=latest_msg['id'],
                defaults={
                    'social_account': account,
                    'type': 'message',
                    'sender_id': latest_msg.get('from', {}).get('id'),
                    'sender_name': latest_msg.get('from', {}).get('name', 'Messenger User'),
                    'content': latest_msg.get('message', ''),
                    'received_at': created_time,
                }
            )
            if created:
                count += 1
    return count


def _sync_instagram_comments(account, page_token):
    """Sync comments from the connected Instagram Business Account posts."""
    page_id = account.platform_account_id
    url = f"https://graph.facebook.com/v22.0/{page_id}"
    params = {
        'access_token': page_token,
        'fields': 'instagram_business_account{id}'
    }
    count = 0
    ig_res = requests.get(url, params=params, timeout=10).json()
    
    if 'error' in ig_res:
        print(f"[Meta API Exception] Instagram Check returned error: {ig_res['error'].get('message')}")
        return 0
        
    ig_id = ig_res.get('instagram_business_account', {}).get('id')
    if not ig_id:
        return 0
        
    media_url = f"https://graph.facebook.com/v22.0/{ig_id}/media"
    media_params = {
        'access_token': page_token,
        'fields': 'id,comments{id,text,username,timestamp}'
    }
    media_res = requests.get(media_url, params=media_params, timeout=15).json()
    
    if 'error' in media_res:
        print(f"[Meta API Exception] Instagram Media returned error: {media_res['error'].get('message')}")
        return 0
        
    media_list = media_res.get('data', [])
    for media in media_list:
        comments = media.get('comments', {}).get('data', [])
        for comment in comments:
            created_time = parse_datetime(comment.get('timestamp'))
            obj, created = InboxItem.objects.update_or_create(
                item_id=comment['id'],
                defaults={
                    'social_account': account,
                    'type': 'comment',
                    'sender_id': comment.get('id'),
                    'sender_name': comment.get('username', 'IG User'),
                    'content': comment.get('text', ''),
                    'received_at': created_time,
                }
            )
            if created:
                count += 1
    return count


def _sync_twitter_mentions(account, token):
    """Sync Twitter Mentions/Replies using API v2."""
    twitter_id = account.platform_account_id
    url = f"https://api.twitter.com/2/users/{twitter_id}/mentions"
    headers = {"Authorization": f"Bearer {token}"}
    params = {"tweet.fields": "created_at,author_id", "max_results": 10}
    count = 0
    res = requests.get(url, headers=headers, params=params, timeout=15).json()
    
    if 'errors' in res or 'error' in res:
         print(f"[Twitter API Exception] Twitter returned error: {res.get('errors') or res.get('error')}")
         return 0
         
    tweets = res.get('data', [])
    for tweet in tweets:
        created_time = parse_datetime(tweet.get('created_at'))
        obj, created = InboxItem.objects.update_or_create(
            item_id=tweet['id'],
            defaults={
                'social_account': account,
                'type': 'message',
                'sender_id': tweet.get('author_id'),
                'sender_name': f"X User ({tweet.get('author_id')[:8]})",
                'content': tweet.get('text', ''),
                'received_at': created_time,
            }
        )
        if created:
            count += 1
    return count


def _sync_linkedin_comments(account, token):
    """Sync LinkedIn Comments on User Posts using API v2."""
    author_id = account.platform_account_id
    headers = {
        "Authorization": f"Bearer {token}",
        "X-Restli-Protocol-Version": "2.0.0"
    }
    count = 0
    posts_url = f"https://api.linkedin.com/v2/posts?author=urn:li:person:{author_id}&count=10"
    posts_res = requests.get(posts_url, headers=headers, timeout=15).json()
    
    if 'message' in posts_res:
        print(f"[LinkedIn API Exception] LinkedIn returned error: {posts_res.get('message')}")
        return 0
        
    posts = posts_res.get('elements', [])
    for post in posts:
        post_urn = post['id']
        
        comments_url = f"https://api.linkedin.com/v2/socialActions/{post_urn}/comments"
        comments_res = requests.get(comments_url, headers=headers, timeout=10).json()
        
        if 'message' in comments_res:
            continue
            
        comments = comments_res.get('elements', [])
        for comment in comments:
            commenter_urn = comment.get('actor')
            if f"urn:li:person:{author_id}" in commenter_urn:
                continue
                
            comment_id = comment['id']
            message = comment.get('message', {}).get('text', '')
            created_time = timezone.now()
            
            obj, created = InboxItem.objects.update_or_create(
                item_id=comment_id,
                defaults={
                    'social_account': account,
                    'type': 'comment',
                    'sender_id': commenter_urn,
                    'sender_name': "LinkedIn Member",
                    'content': message,
                    'received_at': created_time,
                }
            )
            if created:
                count += 1
    return count


@login_required
def send_inbox_reply(request, item_id):
    """Reply live to a comment/message on Facebook, Instagram, Twitter/X, and LinkedIn!"""
    if request.method != 'POST':
        return redirect('inbox_list')
        
    item = get_object_or_404(InboxItem, id=item_id, social_account__connected_by=request.user)
    reply_content = request.POST.get('message', '').strip()
    
    if not reply_content:
        messages.error(request, "Reply content cannot be empty!")
        return redirect('inbox_list')
        
    token = item.social_account.access_token
    if not token:
        messages.error(request, "Access token not found. Please reconnect account.")
        return redirect('inbox_list')
        
    success = False
    error_msg = ""
    
    try:
        # ফেসবুক এবং ইনস্টাগ্রাম লাইভ রিপ্লাই ফ্লো
        if item.social_account.platform in ['facebook', 'instagram']:
            base_url = "https://graph.facebook.com/v22.0"
            if item.type == 'comment':
                endpoint = f"{base_url}/{item.item_id}/comments" if item.social_account.platform == 'facebook' else f"{base_url}/{item.item_id}/replies"
                res = requests.post(endpoint, data={'message': reply_content, 'access_token': token}, timeout=15).json()
                if 'id' in res:
                    success = True
                else:
                    error_msg = res.get('error', {}).get('message', 'Unknown API Error')
            elif item.type == 'message':
                endpoint = f"{base_url}/me/messages"
                payload = {
                    'recipient': {'id': item.sender_id},
                    'message': {'text': reply_content}
                }
                res = requests.post(endpoint, params={'access_token': token}, json=payload, timeout=15).json()
                if 'message_id' in res or 'recipient_id' in res:
                    success = True
                else:
                    error_msg = res.get('error', {}).get('message', 'Unknown API Error')
                    
        # নতুন: টুইটার/X লাইভ রিপ্লাই ফ্লো (টুইটের ইন-রিপ্লাই-টু আকারে পোস্ট করা)
        elif item.social_account.platform == 'twitter':
            endpoint = "https://api.twitter.com/2/tweets"
            headers = {
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            }
            payload = {
                "text": reply_content,
                "reply": {
                    "in_reply_to_tweet_id": item.item_id # কাস্টমার টুইটের কমেন্ট থ্রেডে রিপ্লাই
                }
            }
            res = requests.post(endpoint, headers=headers, json=payload, timeout=15)
            if res.status_code == 201:
                success = True
            else:
                error_msg = res.json().get('detail', 'X API Reply Error')
                
        # নতুন: লিঙ্কডইন লাইভ রিপ্লাই ফ্লো (লিঙ্কডইন সোশ্যাল কমেন্ট থ্রেডে রিপ্লাই করা)
        elif item.social_account.platform == 'linkedin':
            endpoint = f"https://api.linkedin.com/v2/socialActions/{item.item_id}/comments"
            headers = {
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
                "X-Restli-Protocol-Version": "2.0.0"
            }
            payload = {
                "actor": f"urn:li:person:{item.social_account.platform_account_id}",
                "message": {"text": reply_content}
            }
            res = requests.post(endpoint, headers=headers, json=payload, timeout=15)
            if res.status_code in [200, 201]:
                success = True
            else:
                error_msg = res.json().get('message', 'LinkedIn Reply Error')
                
        if success:
            # লাইভ রিপ্লাইয়ের কপি ডাটাবেজে রিলেশন হিসেবে সেভ হচ্ছে
            Reply.objects.create(
                inbox_item=item,
                content=reply_content,
                sent_by=request.user
            )
            item.is_replied = True
            item.is_read = True
            item.save()
            messages.success(request, "Reply successfully posted live to social media!")
        else:
            messages.error(request, f"Failed to send reply: {error_msg}")
            
    except requests.RequestException as e:
        messages.error(request, f"Network error: {str(e)}")
        
    return redirect('inbox_list')


@login_required
def mark_read_ajax(request, item_id):
    """AJAX endpoint to mark an inbox item as read."""
    item = get_object_or_404(InboxItem, id=item_id, social_account__connected_by=request.user)
    item.is_read = True
    item.save(update_fields=['is_read'])
    return JsonResponse({'status': 'success'})