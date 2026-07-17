import requests
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse
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
    """Sync comments and messages directly from Facebook and Instagram APIs."""
    connected_accounts = SocialAccount.objects.filter(connected_by=request.user, status='connected')
    
    if not connected_accounts.exists():
        messages.warning(request, "Please connect at least one social media account before syncing the inbox.")
        return redirect('inbox_list') # নেমস্পেস ছাড়া গ্লোবাল ইউআরএল দেওয়া হলো
        
    synced_count = 0
    adapter = FacebookAdapter()
    
    for account in connected_accounts:
        page_token, error = adapter.get_page_token(account)
        if error:
            continue
            
        if account.platform == 'facebook':
            # Sync Facebook Page comments and Messenger messages
            synced_count += _sync_facebook_comments(account, page_token)
            synced_count += _sync_facebook_messages(account, page_token)
        elif account.platform == 'instagram':
            # Sync Instagram Business Account comments
            synced_count += _sync_instagram_comments(account, page_token)
            
    messages.success(request, f"Successfully synced {synced_count} new items to your inbox!")
    return redirect('inbox_list') # নেমস্পেস ছাড়া গ্লোবাল ইউআরএল দেওয়া হলো


def _sync_facebook_comments(account, page_token):
    """Sync comments from the Facebook Page feed."""
    page_id = account.platform_account_id
    url = f"https://graph.facebook.com/v22.0/{page_id}/feed"
    params = {
        'access_token': page_token,
        'fields': 'id,comments{id,message,from,created_time}'
    }
    count = 0
    try:
        response = requests.get(url, params=params, timeout=15).json()
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
    except Exception:
        pass
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
    try:
        response = requests.get(url, params=params, timeout=15).json()
        conversations = response.get('data', [])
        for conv in conversations:
            messages_list = conv.get('messages', {}).get('data', [])
            if messages_list:
                # Get the latest message in the conversation
                latest_msg = messages_list[0]
                # Ignore messages sent by the Page itself
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
    except Exception:
        pass
    return count


def _sync_instagram_comments(account, page_token):
    """Sync comments from the connected Instagram Business Account posts."""
    page_id = account.platform_account_id
    # Fetch the linked Instagram Business Account ID
    url = f"https://graph.facebook.com/v22.0/{page_id}"
    params = {
        'access_token': page_token,
        'fields': 'instagram_business_account{id}'
    }
    count = 0
    try:
        ig_res = requests.get(url, params=params, timeout=10).json()
        ig_id = ig_res.get('instagram_business_account', {}).get('id')
        if not ig_id:
            return 0
            
        # Fetch comments from Instagram media list
        media_url = f"https://graph.facebook.com/v22.0/{ig_id}/media"
        media_params = {
            'access_token': page_token,
            'fields': 'id,comments{id,text,username,timestamp}'
        }
        media_res = requests.get(media_url, params=media_params, timeout=15).json()
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
    except Exception:
        pass
    return count


@login_required
def send_inbox_reply(request, item_id):
    """Reply to an inbox comment or message (saves to DB and posts live to the platform)."""
    if request.method != 'POST':
        return redirect('inbox_list')
        
    item = get_object_or_404(InboxItem, id=item_id, social_account__connected_by=request.user)
    reply_content = request.POST.get('message', '').strip()
    
    if not reply_content:
        messages.error(request, "Reply content cannot be empty!")
        return redirect('inbox_list')
        
    adapter = FacebookAdapter()
    page_token, error = adapter.get_page_token(item.social_account)
    
    if error:
        messages.error(request, f"Access token not found: {error}")
        return redirect('inbox_list')
        
    base_url = "https://graph.facebook.com/v22.0"
    success = False
    error_msg = ""
    
    try:
        # Reply live to a Facebook or Instagram comment
        if item.type == 'comment':
            endpoint = f"{base_url}/{item.item_id}/comments" if item.social_account.platform == 'facebook' else f"{base_url}/{item.item_id}/replies"
            res = requests.post(endpoint, data={'message': reply_content, 'access_token': page_token}, timeout=15).json()
            if 'id' in res:
                success = True
            else:
                error_msg = res.get('error', {}).get('message', 'Unknown API Error')
                
        # Reply live to a Facebook Messenger direct message
        elif item.type == 'message':
            endpoint = f"{base_url}/me/messages"
            payload = {
                'recipient': {'id': item.sender_id},
                'message': {'text': reply_content}
            }
            res = requests.post(endpoint, params={'access_token': page_token}, json=payload, timeout=15).json()
            if 'message_id' in res or 'recipient_id' in res:
                success = True
            else:
                error_msg = res.get('error', {}).get('message', 'Unknown API Error')
                
        if success:
            # Save a copy of the live reply to the local database
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