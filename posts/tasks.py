import os
import time
import requests
from celery import shared_task
from django.utils import timezone
from .models import Post, PostPlatformStatus
from social_accounts.models import SocialAccount

@shared_task
def publish_post_task(post_id, account_id):
    """Universal Publisher for Facebook, Instagram, LinkedIn, and Twitter/X with Video Stream Fix"""
    try:
        post = Post.objects.get(id=post_id)
        account = SocialAccount.objects.get(id=account_id)
        platform_status = PostPlatformStatus.objects.get(post=post, social_account=account)
    except Exception as e:
        print(f"[Publish Task Error]: Object not found - {e}")
        return False

    platform = account.platform
    page_id = account.platform_account_id
    token = account.access_token

    # 📸 / 🎥 মিডিয়া ফিল্টার
    media_url = None
    if post.media_file:
        media_url = post.media_file.url if hasattr(post.media_file, 'url') else str(post.media_file)

    is_video = (post.media_type == 'video')

    # 🛑 ১. ভিডিও ইউআরএল ফিক্স (ক্লাউডিনারির ভিডিও ইউআরএল মেটা বটের জন্য ক্লিন করা)
    if is_video and media_url:
        # ক্লাউডিনারির ইমেজ অ্যান্ডপয়েন্ট থাকলে ভিডিও অ্যান্ডপয়েন্টে কনভার্ট করা
        if '/image/upload/' in media_url:
            media_url = media_url.replace('/image/upload/', '/video/upload/')

        clean_url = media_url.split('?')[0]
        if not (clean_url.endswith('.mp4') or clean_url.endswith('.mov')):
            clean_url = clean_url + '.mp4'
        media_url = clean_url

    success = False
    error_msg = None
    published_id = None

    try:
        # ──────────────────────────────────────────
        # 🔵 1. FACEBOOK PUBLISHING LOGIC
        # ──────────────────────────────────────────
        if platform == 'facebook':
            if is_video and media_url:
                url = f"https://graph.facebook.com/v22.0/{page_id}/videos"
                payload = {'file_url': media_url, 'description': post.content or '', 'access_token': token}
                res = requests.post(url, data=payload, timeout=35).json()
            elif media_url:
                url = f"https://graph.facebook.com/v22.0/{page_id}/photos"
                payload = {'url': media_url, 'caption': post.content or '', 'access_token': token}
                res = requests.post(url, data=payload, timeout=20).json()
            else:
                url = f"https://graph.facebook.com/v22.0/{page_id}/feed"
                payload = {'message': post.content or '', 'access_token': token}
                res = requests.post(url, data=payload, timeout=15).json()

            if 'id' in res:
                success = True
                published_id = res['id']
            else:
                error_msg = res.get('error', {}).get('message', 'Facebook publish failed')

        # ──────────────────────────────────────────
        # 📸 2. INSTAGRAM PUBLISHING LOGIC
        # ──────────────────────────────────────────
        elif platform == 'instagram':
            ig_res = requests.get(
                f"https://graph.facebook.com/v22.0/{page_id}",
                params={'access_token': token, 'fields': 'instagram_business_account'},
                timeout=10
            ).json()
            ig_id = ig_res.get('instagram_business_account', {}).get('id')

            if not ig_id:
                error_msg = "No Instagram Business account connected to this Facebook Page."
            elif not media_url:
                error_msg = "Instagram requires an Image or Video attachment."
            else:
                # Step A: Container Creation
                container_url = f"https://graph.facebook.com/v22.0/{ig_id}/media"
                c_params = {'access_token': token, 'caption': post.content or ''}

                if is_video:
                    c_params['media_type'] = 'REELS'
                    c_params['video_url'] = media_url
                else:
                    c_params['image_url'] = media_url

                c_res = requests.post(container_url, data=c_params, timeout=20).json()
                creation_id = c_res.get('id')

                if not creation_id:
                    error_msg = c_res.get('error', {}).get('message', 'Instagram container creation failed')
                else:
                    # Step B: Video Status Polling (ইনস্টাগ্রাম ভিডিও প্রসেস হওয়া পর্যন্ত অপেক্ষা)
                    if is_video:
                        status_url = f"https://graph.facebook.com/v22.0/{creation_id}"
                        for _ in range(12):
                            time.sleep(5)
                            s_res = requests.get(status_url, params={'access_token': token, 'fields': 'status_code'}, timeout=10).json()
                            if s_res.get('status_code') == 'FINISHED':
                                break
                            elif s_res.get('status_code') == 'ERROR':
                                error_msg = "Instagram video processing failed."
                                break

                    # Step C: Publish Media
                    if not error_msg:
                        pub_url = f"https://graph.facebook.com/v22.0/{ig_id}/media_publish"
                        pub_res = requests.post(pub_url, data={'access_token': token, 'creation_id': creation_id}, timeout=20).json()

                        if 'id' in pub_res:
                            success = True
                            published_id = pub_res['id']
                        else:
                            error_msg = pub_res.get('error', {}).get('message', 'Instagram publish failed')

        # ──────────────────────────────────────────
        # 💼 3. LINKEDIN PUBLISHING LOGIC
        # ──────────────────────────────────────────
        elif platform == 'linkedin':
            headers = {
                'Authorization': f'Bearer {token}',
                'X-Restli-Protocol-Version': '2.0.0',
                'Content-Type': 'application/json'
            }
            
            payload = {
                "author": f"urn:li:person:{page_id}",
                "lifecycleState": "PUBLISHED",
                "specificContent": {
                    "com.linkedin.ugc.ShareContent": {
                        "shareCommentary": {"text": post.content or ''},
                        "shareMediaCategory": "NONE"
                    }
                },
                "visibility": {"com.linkedin.ugc.MemberNetworkVisibility": "PUBLIC"}
            }
            
            res = requests.post("https://api.linkedin.com/v2/ugcPosts", json=payload, headers=headers, timeout=15).json()
            if 'id' in res:
                success = True
                published_id = res['id']
            else:
                error_msg = res.get('message', 'LinkedIn API error')

        # ──────────────────────────────────────────
        # 🐦 4. TWITTER / X PUBLISHING LOGIC
        # ──────────────────────────────────────────
        elif platform == 'twitter':
            headers = {
                'Authorization': f'Bearer {token}',
                'Content-Type': 'application/json'
            }
            payload = {'text': post.content or ''}
            
            res = requests.post("https://api.twitter.com/2/tweets", json=payload, headers=headers, timeout=15).json()
            if 'data' in res and 'id' in res['data']:
                success = True
                published_id = res['data']['id']
            else:
                error_msg = res.get('detail') or res.get('title') or 'Twitter API error'

    except Exception as ex:
        error_msg = f"Network exception: {str(ex)}"

    # ──────────────────────────────────────────
    # 🎯 REAL-TIME PLATFORM DATABASE STATUS UPDATE
    # ──────────────────────────────────────────
    if success:
        platform_status.status = 'published'
        platform_status.platform_post_id = published_id
        platform_status.error_message = None
        platform_status.save()
    else:
        platform_status.status = 'failed'
        platform_status.error_message = error_msg or 'Publishing failed'
        platform_status.save()

    # ──────────────────────────────────────────
    # 🏆 MASTER POST STATUS SYNC (সবগুলো ফেল মারলে লাল Failed দেখাবে)
    # ──────────────────────────────────────────
    published_count = post.platform_statuses.filter(status='published').count()
    failed_count = post.platform_statuses.filter(status='failed').count()
    total_count = post.platform_statuses.count()

    if failed_count == total_count:
        post.status = 'failed'      # সবগুলো চ্যানেল ফেল মারলে ড্যাশবোর্ডের মেইন ব্যাজ লাল Failed হবে
    elif published_count > 0:
        post.status = 'published'   # অন্তত ১টি চ্যানেল সফল হলে মেইন ব্যাজ সবুজ Published হবে
    else:
        post.status = 'failed'

    post.save()
    return success


@shared_task
def check_and_publish_scheduled_posts():
    """Celery Beat Cron Task to publish due scheduled posts automatically"""
    now = timezone.now()
    due_posts = Post.objects.filter(status='scheduled', scheduled_time__lte=now)

    for post in due_posts:
        post.status = 'processing'
        post.save(update_fields=['status'])
        
        for platform_status in post.platform_statuses.filter(status='scheduled'):
            platform_status.status = 'processing'
            platform_status.save(update_fields=['status'])
            publish_post_task.delay(post.id, platform_status.social_account.id)
            
    return f"Queued {due_posts.count()} due posts for publishing."