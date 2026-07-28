import os
import time
import requests
from celery import shared_task
from django.utils import timezone
from .models import Post, PostPlatformStatus
from social_accounts.models import SocialAccount

def get_media_bytes(post):
    """Fetch binary bytes whether media is stored on Cloudinary OR local disk"""
    if not post.media_file:
        return None

    try:
        # ১. যদি ক্লাউডিনারি বা অনলাইনে সেভ থাকে
        media_str = str(post.media_file.url if hasattr(post.media_file, 'url') else post.media_file)
        if media_str.startswith('http://') or media_str.startswith('https://'):
            res = requests.get(media_str, timeout=20)
            if res.status_code == 200:
                return res.content

        # ২. যদি লোকাল ডিস্কে সেভ থাকে
        if hasattr(post.media_file, 'path') and os.path.exists(post.media_file.path):
            with open(post.media_file.path, 'rb') as f:
                return f.read()
    except Exception as e:
        print(f"[Media Byte Extraction Error]: {e}")

    return None


@shared_task
def publish_post_task(post_id, account_id):
    """Fail-Safe Dual Stream Publisher for Facebook, Instagram, LinkedIn, and Twitter/X"""
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

    media_url = None
    if post.media_file:
        media_url = str(post.media_file.url if hasattr(post.media_file, 'url') else post.media_file)

    is_video = (post.media_type == 'video')

    success = False
    error_msg = None
    published_id = None

    try:
        # ──────────────────────────────────────────
        # 🔵 1. FACEBOOK PUBLISHING
        # ──────────────────────────────────────────
        if platform == 'facebook':
            if is_video and media_url:
                clean_url = media_url.replace('/image/upload/', '/video/upload/').split('?')[0]
                if not (clean_url.endswith('.mp4') or clean_url.endswith('.mov')):
                    clean_url += '.mp4'

                url = f"https://graph.facebook.com/v22.0/{page_id}/videos"
                payload = {'file_url': clean_url, 'description': post.content or '', 'access_token': token}
                res = requests.post(url, data=payload, timeout=40).json()

            elif media_url:
                photo_url = f"https://graph.facebook.com/v22.0/{page_id}/photos"
                raw_bytes = get_media_bytes(post)

                if raw_bytes:
                    files = {'source': ('image.jpg', raw_bytes, 'image/jpeg')}
                    data = {'caption': post.content or '', 'access_token': token}
                    res = requests.post(photo_url, data=data, files=files, timeout=30).json()
                else:
                    res = {'error': {'message': 'Could not read media file for Facebook'}}
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
        # 📸 2. INSTAGRAM PUBLISHING
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
                container_url = f"https://graph.facebook.com/v22.0/{ig_id}/media"
                c_params = {'access_token': token, 'caption': post.content or ''}

                if is_video:
                    clean_url = media_url.replace('/image/upload/', '/video/upload/').split('?')[0]
                    if not clean_url.endswith('.mp4'):
                        clean_url += '.mp4'
                    c_params['media_type'] = 'REELS'
                    c_params['video_url'] = clean_url
                else:
                    clean_url = media_url.split('?')[0]
                    if not (clean_url.endswith('.jpg') or clean_url.endswith('.png')):
                        clean_url += '.jpg'
                    c_params['image_url'] = clean_url

                c_res = requests.post(container_url, data=c_params, timeout=20).json()
                creation_id = c_res.get('id')

                if not creation_id:
                    error_msg = c_res.get('error', {}).get('message', 'Instagram container creation failed')
                else:
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

                    if not error_msg:
                        pub_url = f"https://graph.facebook.com/v22.0/{ig_id}/media_publish"
                        pub_res = requests.post(pub_url, data={'access_token': token, 'creation_id': creation_id}, timeout=20).json()

                        if 'id' in pub_res:
                            success = True
                            published_id = pub_res['id']
                        else:
                            error_msg = pub_res.get('error', {}).get('message', 'Instagram publish failed')

        # ──────────────────────────────────────────
        # 💼 3. LINKEDIN PUBLISHING
        # ──────────────────────────────────────────
        elif platform == 'linkedin':
            headers = {
                'Authorization': f'Bearer {token}',
                'X-Restli-Protocol-Version': '2.0.0',
                'Content-Type': 'application/json'
            }

            if media_url and not is_video:
                register_url = "https://api.linkedin.com/v2/assets?action=registerUpload"
                reg_payload = {
                    "registerUploadRequest": {
                        "recipes": ["urn:li:digitalmediaRecipe:feedshare-image"],
                        "owner": f"urn:li:person:{page_id}",
                        "serviceRelationships": [{"relationshipType": "OWNER", "identifier": "urn:li:userGeneratedContent"}]
                    }
                }
                reg_res = requests.post(register_url, json=reg_payload, headers=headers, timeout=15).json()
                
                upload_url = reg_res.get('value', {}).get('uploadMechanism', {}).get('com.linkedin.digitalmedia.uploading.MediaUploadHttpRequest', {}).get('uploadUrl')
                asset_id = reg_res.get('value', {}).get('asset')

                if upload_url and asset_id:
                    img_bytes = get_media_bytes(post)
                    if img_bytes:
                        up_headers = {'Authorization': f'Bearer {token}', 'Content-Type': 'image/jpeg'}
                        requests.put(upload_url, data=img_bytes, headers=up_headers, timeout=25)

                        ugc_payload = {
                            "author": f"urn:li:person:{page_id}",
                            "lifecycleState": "PUBLISHED",
                            "specificContent": {
                                "com.linkedin.ugc.ShareContent": {
                                    "shareCommentary": {"text": post.content or ''},
                                    "shareMediaCategory": "IMAGE",
                                    "media": [{"status": "READY", "media": asset_id}]
                                }
                            },
                            "visibility": {"com.linkedin.ugc.MemberNetworkVisibility": "PUBLIC"}
                        }
                        res = requests.post("https://api.linkedin.com/v2/ugcPosts", json=ugc_payload, headers=headers, timeout=15).json()
                    else:
                        res = {'message': 'LinkedIn media byte download failed'}
                else:
                    res = {'message': 'LinkedIn asset registration failed'}
            else:
                ugc_payload = {
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
                res = requests.post("https://api.linkedin.com/v2/ugcPosts", json=ugc_payload, headers=headers, timeout=15).json()

            if 'id' in res:
                success = True
                published_id = res['id']
            else:
                error_msg = res.get('message', 'LinkedIn API error')

        # ──────────────────────────────────────────
        # 🐦 4. TWITTER PUBLISHING
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
    # 🎯 REAL-TIME PLATFORM STATUS UPDATE
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

    # 🏆 MASTER POST STATUS SYNC
    published_count = post.platform_statuses.filter(status='published').count()
    failed_count = post.platform_statuses.filter(status='failed').count()
    total_count = post.platform_statuses.count()

    if failed_count == total_count:
        post.status = 'failed'
    elif published_count > 0:
        post.status = 'published'
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