import requests
import json
import hashlib
import hmac
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse, HttpResponse
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django.views.decorators.csrf import csrf_exempt
from social_accounts.models import SocialAccount
from integrations.facebook_adapter import FacebookAdapter
from .models import InboxItem, Reply


@login_required
def inbox_list(request):
    selected_platform = request.GET.get('platform', '')
    selected_type = request.GET.get('type', '')
    active_sender_id = request.GET.get('sender_id', '')
    active_account_id = request.GET.get('account_id', '')

    if request.user.is_superuser or getattr(request.user, 'user_type', None) == 'admin':
        items = InboxItem.objects.all()
    else:
        items = InboxItem.objects.filter(social_account__permitted_users=request.user)

    if selected_platform:
        items = items.filter(social_account__platform=selected_platform)
    if selected_type:
        items = items.filter(type=selected_type)

    from django.db.models import Max, Count, Q
    conversations_qs = items.values(
        'sender_id', 'sender_name', 'social_account__id',
        'social_account__platform', 'social_account__account_name', 'type'
    ).annotate(
        last_message_time=Max('received_at'),
        message_count=Count('id'),
        unread_count=Count('id', filter=Q(is_read=False)),
    ).order_by('-unread_count', '-last_message_time')

    active_conversation = None
    conversation_messages = []

    if active_sender_id and active_account_id:
        active_conversation = {
            'sender_id': active_sender_id,
            'account_id': active_account_id,
        }
        conversation_messages = items.filter(
            sender_id=active_sender_id,
            social_account__id=active_account_id,
        ).order_by('received_at')

        conversation_messages.filter(is_read=False).update(is_read=True)
        active_item = conversation_messages.last()

        if conversation_messages.exists():
            first_msg = conversation_messages.first()
            active_conversation['sender_name'] = first_msg.sender_name
            active_conversation['platform'] = first_msg.social_account.platform
            active_conversation['account_name'] = first_msg.social_account.account_name
            active_conversation['type'] = first_msg.type
            active_conversation['active_item'] = active_item
    elif conversations_qs.exists():
        first_conv = conversations_qs.first()
        active_sender_id = first_conv['sender_id']
        active_account_id = first_conv['social_account__id']
        active_conversation = {
            'sender_id': active_sender_id,
            'account_id': active_account_id,
        }
        conversation_messages = items.filter(
            sender_id=active_sender_id,
            social_account__id=active_account_id,
        ).order_by('received_at')
        conversation_messages.filter(is_read=False).update(is_read=True)
        active_item = conversation_messages.last()
        if conversation_messages.exists():
            first_msg = conversation_messages.first()
            active_conversation['sender_name'] = first_msg.sender_name
            active_conversation['platform'] = first_msg.social_account.platform
            active_conversation['account_name'] = first_msg.social_account.account_name
            active_conversation['type'] = first_msg.type
            active_conversation['active_item'] = active_item

    unread_count = items.filter(is_read=False).count()

    context = {
        'conversations': conversations_qs,
        'active_conversation': active_conversation,
        'conversation_messages': conversation_messages,
        'active_sender_id': active_sender_id,
        'active_account_id': str(active_account_id),
        'selected_platform': selected_platform,
        'selected_type': selected_type,
        'unread_count': unread_count,
    }
    return render(request, 'inbox/inbox_list.html', context)


@login_required
def sync_inbox_data(request):
    if request.user.is_superuser or getattr(request.user, 'user_type', None) == 'admin':
        connected_accounts = SocialAccount.objects.filter(status='connected')
    else:
        connected_accounts = SocialAccount.objects.filter(
            permitted_users=request.user, status='connected'
        )

    if not connected_accounts.exists():
        messages.warning(request, "Please connect at least one social media account.")
        return redirect('inbox_list')

    synced_count = 0
    adapter = FacebookAdapter()

    for account in connected_accounts:
        page_token, error = adapter.get_page_token(account)
        if error:
            continue

        try:
            if account.platform == 'facebook':
                try:
                    synced_count += _sync_facebook_comments(account, page_token)
                except Exception as e:
                    print(f"[FB Comments Error] {account.account_name}: {e}")
                try:
                    synced_count += _sync_facebook_messages(account, page_token)
                except Exception as e:
                    print(f"[FB Messages Error] {account.account_name}: {e}")
            elif account.platform == 'instagram':
                try:
                    synced_count += _sync_instagram_comments(account, page_token)
                except Exception as e:
                    print(f"[IG Comments Error] {account.account_name}: {e}")
                try:
                    synced_count += _sync_instagram_messages(account, page_token)
                except Exception as e:
                    print(f"[IG Messages Error] {account.account_name}: {e}")
            elif account.platform == 'twitter':
                try:
                    synced_count += _sync_twitter_mentions(account, page_token)
                except Exception as e:
                    print(f"[Twitter Error] {account.account_name}: {e}")
            elif account.platform == 'linkedin':
                try:
                    synced_count += _sync_linkedin_comments(account, page_token)
                except Exception as e:
                    print(f"[LinkedIn Error] {account.account_name}: {e}")
        except Exception as e:
            print(f"[General Sync Error] {account.account_name}: {e}")

    messages.success(request, f"Successfully synced {synced_count} new items to your inbox!")
    return redirect('inbox_list')


@login_required
def inbox_live_sync(request):
    """2 second polling এর জন্য lightweight sync endpoint"""
    if not request.headers.get('x-requested-with') == 'XMLHttpRequest':
        return JsonResponse({'error': 'Invalid request'}, status=400)

    if request.user.is_superuser or getattr(request.user, 'user_type', None) == 'admin':
        connected_accounts = SocialAccount.objects.filter(status='connected')
    else:
        connected_accounts = SocialAccount.objects.filter(
            permitted_users=request.user, status='connected'
        )

    synced_count = 0
    adapter = FacebookAdapter()

    for account in connected_accounts:
        page_token, error = adapter.get_page_token(account)
        if error:
            continue
        try:
            if account.platform == 'facebook':
                synced_count += _sync_facebook_messages(account, page_token)
            elif account.platform == 'instagram':
                synced_count += _sync_instagram_messages(account, page_token)
        except Exception as e:
            print(f"[Live Sync Error] {account.account_name}: {e}")

    if request.user.is_superuser or getattr(request.user, 'user_type', None) == 'admin':
        unread = InboxItem.objects.filter(is_read=False).count()
    else:
        unread = InboxItem.objects.filter(
            social_account__permitted_users=request.user,
            is_read=False
        ).count()

    return JsonResponse({
        'synced': synced_count,
        'unread_count': unread,
    })


@csrf_exempt
def facebook_webhook(request):
    """Facebook Webhook — messages ও comments real-time receive করা"""
    if request.method == 'GET':
        verify_token = 'my_secret_webhook_token_2024'
        mode = request.GET.get('hub.mode')
        token = request.GET.get('hub.verify_token')
        challenge = request.GET.get('hub.challenge')

        if mode == 'subscribe' and token == verify_token:
            return HttpResponse(challenge, content_type='text/plain')
        return HttpResponse('Forbidden', status=403)

    elif request.method == 'POST':
        try:
            data = json.loads(request.body)
            print(f"[Webhook] Received: {data}")

            for entry in data.get('entry', []):
                for messaging in entry.get('messaging', []):
                    if 'message' in messaging:
                        _process_webhook_message(messaging)

                for change in entry.get('changes', []):
                    if change.get('field') == 'feed':
                        _process_webhook_comment(change.get('value', {}))
        except Exception as e:
            print(f"[Webhook POST Error] {e}")

        return HttpResponse('OK')

    return HttpResponse('Method not allowed', status=405)


def _process_webhook_message(messaging):
    """Webhook থেকে আসা Messenger message process করা"""
    try:
        sender_id = messaging['sender']['id']
        message = messaging.get('message', {})
        text = message.get('text', '')
        page_id = messaging['recipient']['id']

        if not text:
            return

        account = SocialAccount.objects.filter(
            platform='facebook',
            platform_account_id=page_id,
            status='connected'
        ).first()

        if not account:
            return

        msg_id = message.get('mid', f"wb_{sender_id}_{timezone.now().timestamp()}")

        InboxItem.objects.update_or_create(
            item_id=msg_id,
            defaults={
                'social_account': account,
                'type': 'message',
                'sender_id': sender_id,
                'sender_name': f"User {sender_id[:8]}",
                'content': text,
                'received_at': timezone.now(),
                'is_read': False,
            }
        )
        print(f"[Webhook] Message saved from {sender_id}")
    except Exception as e:
        print(f"[Webhook Message Error] {e}")


def _process_webhook_comment(value):
    """Webhook থেকে আসা comment process করা"""
    try:
        if value.get('item') != 'comment':
            return

        page_id = value.get('page_id', '')
        sender_name = value.get('from', {}).get('name', 'Facebook User')
        sender_id = value.get('from', {}).get('id', '')
        comment_id = value.get('comment_id', '')
        message = value.get('message', '')

        account = SocialAccount.objects.filter(
            platform='facebook',
            platform_account_id=page_id,
            status='connected'
        ).first()

        if not account or not comment_id:
            return

        InboxItem.objects.update_or_create(
            item_id=comment_id,
            defaults={
                'social_account': account,
                'type': 'comment',
                'sender_id': sender_id,
                'sender_name': sender_name,
                'content': message,
                'received_at': timezone.now(),
                'is_read': False,
            }
        )
        print(f"[Webhook] Comment saved from {sender_name}")
    except Exception as e:
        print(f"[Webhook Comment Error] {e}")


def _sync_facebook_messages(account, page_token):
    """Facebook Page Messenger DMs sync।"""
    page_id = account.platform_account_id
    url = f"https://graph.facebook.com/v22.0/{page_id}/conversations"
    params = {
        'access_token': page_token,
        'fields': 'participants,messages{message,from,created_time,id}',
        'limit': 10,
    }
    count = 0
    response = requests.get(url, params=params, timeout=15).json()

    if 'error' in response:
        print(f"[FB Messages] {account.account_name}: {response['error'].get('message')}")
        return 0

    for conversation in response.get('data', []):
        messages_data = conversation.get('messages', {}).get('data', [])
        participants = conversation.get('participants', {}).get('data', [])
        sender = next(
            (p for p in participants if p.get('id') != page_id),
            None
        )
        if not sender:
            continue

        sender_name = sender.get('name', 'Facebook User')
        sender_id = sender.get('id', '')

        for msg in messages_data:
            if msg.get('from', {}).get('id') == page_id:
                continue
            created_time = parse_datetime(msg.get('created_time'))
            _, created = InboxItem.objects.update_or_create(
                item_id=msg['id'],
                defaults={
                    'social_account': account,
                    'type': 'message',
                    'sender_id': sender_id,
                    'sender_name': sender_name,
                    'content': msg.get('message', ''),
                    'received_at': created_time,
                }
            )
            if created:
                count += 1
    return count


def _sync_instagram_messages(account, page_token):
    """Instagram DMs sync।"""
    ig_id = account.platform_account_id
    if not ig_id:
        return 0

    url = f"https://graph.facebook.com/v22.0/{ig_id}/conversations"
    params = {
        'access_token': page_token,
        'fields': 'participants,messages{message,from,created_time,id}',
        'platform': 'instagram',
        'limit': 10,
    }
    count = 0
    response = requests.get(url, params=params, timeout=15).json()

    if 'error' in response:
        print(f"[IG Messages] {account.account_name}: {response['error'].get('message')}")
        return 0

    for conversation in response.get('data', []):
        messages_data = conversation.get('messages', {}).get('data', [])
        participants = conversation.get('participants', {}).get('data', [])
        sender = next(
            (p for p in participants if p.get('id') != ig_id),
            None
        )
        if not sender:
            continue

        sender_name = sender.get('name', 'Instagram User')
        sender_id = sender.get('id', '')

        for msg in messages_data:
            if msg.get('from', {}).get('id') == ig_id:
                continue
            created_time = parse_datetime(msg.get('created_time'))
            _, created = InboxItem.objects.update_or_create(
                item_id=msg['id'],
                defaults={
                    'social_account': account,
                    'type': 'message',
                    'sender_id': sender_id,
                    'sender_name': sender_name,
                    'content': msg.get('message', ''),
                    'received_at': created_time,
                }
            )
            if created:
                count += 1
    return count


def _sync_facebook_comments(account, page_token):
    """Facebook Page published posts থেকে comments sync।"""
    page_id = account.platform_account_id
    url = f"https://graph.facebook.com/v22.0/{page_id}/published_posts"
    params = {
        'access_token': page_token,
        'fields': 'id,comments{id,message,from,created_time}',
        'limit': 10,
    }
    count = 0
    response = requests.get(url, params=params, timeout=15).json()

    if 'error' in response:
        print(f"[FB Comments] {account.account_name}: {response['error'].get('message')}")
        return 0

    for post in response.get('data', []):
        for comment in post.get('comments', {}).get('data', []):
            if comment.get('from', {}).get('id') == page_id:
                continue
            created_time = parse_datetime(comment.get('created_time'))
            _, created = InboxItem.objects.update_or_create(
                item_id=comment['id'],
                defaults={
                    'social_account': account,
                    'type': 'comment',
                    'sender_id': comment.get('from', {}).get('id', ''),
                    'sender_name': comment.get('from', {}).get('name', 'FB User'),
                    'content': comment.get('message', ''),
                    'received_at': created_time,
                }
            )
            if created:
                count += 1
    return count


def _sync_instagram_comments(account, page_token):
    """Instagram media comments sync।"""
    ig_id = account.platform_account_id
    if not ig_id:
        return 0

    media_url = f"https://graph.facebook.com/v22.0/{ig_id}/media"
    media_params = {
        'access_token': page_token,
        'fields': 'id,comments{id,text,username,timestamp}',
        'limit': 10,
    }
    count = 0
    media_res = requests.get(media_url, params=media_params, timeout=15).json()

    if 'error' in media_res:
        print(f"[IG Comments] {account.account_name}: {media_res['error'].get('message')}")
        return 0

    for media in media_res.get('data', []):
        for comment in media.get('comments', {}).get('data', []):
            created_time = parse_datetime(comment.get('timestamp'))
            _, created = InboxItem.objects.update_or_create(
                item_id=comment['id'],
                defaults={
                    'social_account': account,
                    'type': 'comment',
                    'sender_id': comment.get('id', ''),
                    'sender_name': comment.get('username', 'IG User'),
                    'content': comment.get('text', ''),
                    'received_at': created_time,
                }
            )
            if created:
                count += 1
    return count


def _sync_twitter_mentions(account, token):
    """Twitter mentions sync।"""
    twitter_id = account.platform_account_id
    url = f"https://api.twitter.com/2/users/{twitter_id}/mentions"
    headers = {"Authorization": f"Bearer {token}"}
    params = {"tweet.fields": "created_at,author_id", "max_results": 10}
    count = 0
    res = requests.get(url, headers=headers, params=params, timeout=15).json()

    if 'errors' in res or 'error' in res:
        print(f"[Twitter] {account.account_name}: {res.get('errors') or res.get('error')}")
        return 0

    for tweet in res.get('data', []):
        created_time = parse_datetime(tweet.get('created_at'))
        _, created = InboxItem.objects.update_or_create(
            item_id=tweet['id'],
            defaults={
                'social_account': account,
                'type': 'message',
                'sender_id': tweet.get('author_id', ''),
                'sender_name': f"X User ({tweet.get('author_id', '')[:8]})",
                'content': tweet.get('text', ''),
                'received_at': created_time,
            }
        )
        if created:
            count += 1
    return count


def _sync_linkedin_comments(account, token):
    """LinkedIn post comments sync।"""
    author_id = account.platform_account_id
    headers = {
        "Authorization": f"Bearer {token}",
        "X-Restli-Protocol-Version": "2.0.0"
    }
    count = 0
    posts_url = f"https://api.linkedin.com/v2/posts?author=urn:li:person:{author_id}&count=10"
    posts_res = requests.get(posts_url, headers=headers, timeout=15).json()

    if 'message' in posts_res:
        print(f"[LinkedIn] {account.account_name}: {posts_res.get('message')}")
        return 0

    for post in posts_res.get('elements', []):
        post_urn = post['id']
        comments_url = f"https://api.linkedin.com/v2/socialActions/{post_urn}/comments"
        comments_res = requests.get(comments_url, headers=headers, timeout=10).json()

        if 'message' in comments_res:
            continue

        for comment in comments_res.get('elements', []):
            commenter_urn = comment.get('actor', '')
            if f"urn:li:person:{author_id}" in commenter_urn:
                continue
            _, created = InboxItem.objects.update_or_create(
                item_id=comment['id'],
                defaults={
                    'social_account': account,
                    'type': 'comment',
                    'sender_id': commenter_urn,
                    'sender_name': "LinkedIn Member",
                    'content': comment.get('message', {}).get('text', ''),
                    'received_at': timezone.now(),
                }
            )
            if created:
                count += 1
    return count


@login_required
def send_inbox_reply(request, item_id):
    """Comment/Message-এ live reply পাঠানো হচ্ছে।"""
    if request.method != 'POST':
        return redirect('inbox_list')

    if request.user.is_superuser or getattr(request.user, 'user_type', None) == 'admin':
        item = get_object_or_404(InboxItem, id=item_id)
    else:
        item = get_object_or_404(
            InboxItem, id=item_id,
            social_account__permitted_users=request.user
        )

    reply_content = request.POST.get('message', '').strip()
    if not reply_content:
        messages.error(request, "Reply content cannot be empty!")
        return redirect('inbox_list')

    platform = item.social_account.platform
    page_id = item.social_account.platform_account_id

    if platform in ['facebook', 'instagram']:
        adapter = FacebookAdapter()
        token, error = adapter.get_page_token(item.social_account)
        if error:
            messages.error(request, f"Access token error: {error}")
            return redirect('inbox_list')
    else:
        token = item.social_account.access_token

    if not token:
        messages.error(request, "Access token not found. Please reconnect account.")
        return redirect('inbox_list')

    success = False
    error_msg = ""

    try:
        base_url = "https://graph.facebook.com/v22.0"

        if platform == 'facebook':
            if item.type == 'comment':
                res = requests.post(
                    f"{base_url}/{item.item_id}/comments",
                    data={'message': reply_content, 'access_token': token},
                    timeout=15
                ).json()
                success = 'id' in res
                if not success:
                    error_msg = res.get('error', {}).get('message', 'Unknown error')

            elif item.type == 'message':
                res = requests.post(
                    f"{base_url}/{page_id}/messages",
                    params={'access_token': token},
                    json={
                        'recipient': {'id': item.sender_id},
                        'message': {'text': reply_content},
                        'messaging_type': 'RESPONSE',
                    },
                    timeout=15
                ).json()
                success = 'message_id' in res or 'recipient_id' in res
                if not success:
                    error_msg = res.get('error', {}).get('message', 'Messenger reply failed')

        elif platform == 'instagram':
            if item.type == 'comment':
                res = requests.post(
                    f"{base_url}/{item.item_id}/replies",
                    data={'message': reply_content, 'access_token': token},
                    timeout=15
                ).json()
                success = 'id' in res
                if not success:
                    error_msg = res.get('error', {}).get('message', 'Instagram reply failed')

            elif item.type == 'message':
                res = requests.post(
                    f"{base_url}/me/messages",
                    params={'access_token': token},
                    json={
                        'recipient': {'id': item.sender_id},
                        'message': {'text': reply_content},
                        'messaging_type': 'RESPONSE',
                    },
                    timeout=15
                ).json()
                success = 'message_id' in res or 'recipient_id' in res
                if not success:
                    error_msg = res.get('error', {}).get('message', 'Instagram DM reply failed')

        elif platform == 'twitter':
            res = requests.post(
                "https://api.twitter.com/2/tweets",
                headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
                json={"text": reply_content, "reply": {"in_reply_to_tweet_id": item.item_id}},
                timeout=15
            )
            success = res.status_code == 201
            if not success:
                error_msg = res.json().get('detail', 'X API Reply Error')

        elif platform == 'linkedin':
            res = requests.post(
                f"https://api.linkedin.com/v2/socialActions/{item.item_id}/comments",
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json",
                    "X-Restli-Protocol-Version": "2.0.0"
                },
                json={"actor": f"urn:li:person:{page_id}", "message": {"text": reply_content}},
                timeout=15
            )
            success = res.status_code in [200, 201]
            if not success:
                error_msg = res.json().get('message', 'LinkedIn Reply Error')

        if success:
            Reply.objects.create(inbox_item=item, content=reply_content, sent_by=request.user)
            item.is_replied = True
            item.is_read = True
            item.save(update_fields=['is_replied', 'is_read'])
            messages.success(request, "Reply posted successfully!")
        else:
            messages.error(request, f"Failed to send reply: {error_msg}")

    except requests.RequestException as e:
        messages.error(request, f"Network error: {str(e)}")

    return redirect('inbox_list')


@login_required
def mark_read_ajax(request, item_id):
    if request.user.is_superuser or getattr(request.user, 'user_type', None) == 'admin':
        item = get_object_or_404(InboxItem, id=item_id)
    else:
        item = get_object_or_404(
            InboxItem, id=item_id,
            social_account__permitted_users=request.user
        )
    item.is_read = True
    item.save(update_fields=['is_read'])
    return JsonResponse({'status': 'success'})