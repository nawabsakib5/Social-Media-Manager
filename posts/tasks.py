import time
import requests
from celery import shared_task
from django.utils import timezone
from .models import Post, PostPlatformStatus
from social_accounts.models import SocialAccount


@shared_task
def publish_post_task(post_id, account_id):
    """Adapter-based publisher — সব platform-এর logic আলাদা adapter-এ"""
    try:
        post = Post.objects.get(id=post_id)
        account = SocialAccount.objects.get(id=account_id)
        platform_status = PostPlatformStatus.objects.get(
            post=post, social_account=account
        )
    except Exception as e:
        print(f"[Publish Task Error]: Object not found - {e}")
        return False

    # Processing status set করা হচ্ছে
    platform_status.status = 'processing'
    platform_status.error_message = None
    platform_status.save(update_fields=['status', 'error_message'])

    success = False
    error_msg = None
    published_id = None

    try:
        from integrations import get_social_adapter
        adapter = get_social_adapter(account)
        success, result = adapter.publish_post(post, platform_status)

        if success:
            published_id = result
        else:
            error_msg = result

    except ValueError as e:
        # Adapter registry-তে platform না থাকলে (unsupported platform)
        error_msg = str(e)
        print(f"[Publish Task]: {error_msg}")

    except Exception as ex:
        error_msg = f"Network exception: {str(ex)}"
        print(f"[Publish Task Exception]: {ex}")

    # ── Platform status update ──
    if success:
        platform_status.status = 'published'
        platform_status.platform_post_id = published_id
        platform_status.error_message = None
        platform_status.published_at = timezone.now()
        platform_status.save(update_fields=[
            'status', 'platform_post_id', 'error_message', 'published_at'
        ])
    else:
        platform_status.status = 'failed'
        platform_status.error_message = error_msg or 'Publishing failed'
        platform_status.save(update_fields=['status', 'error_message'])

    # ── Master post status sync ──
    all_statuses = list(
        post.platform_statuses.values_list('status', flat=True)
    )
    total = len(all_statuses)
    published = all_statuses.count('published')
    failed = all_statuses.count('failed')

    if failed == total:
        post.status = 'failed'
    elif published > 0:
        post.status = 'published'
    else:
        post.status = 'scheduled'

    post.save(update_fields=['status'])
    return success


@shared_task
def check_and_publish_scheduled_posts():
    """Celery Beat Cron Task — due scheduled posts publish করা"""
    now = timezone.now()
    due_posts = Post.objects.filter(
        status='scheduled',
        scheduled_time__lte=now
    )

    count = 0
    for post in due_posts:
        for platform_status in post.platform_statuses.filter(status='scheduled'):
            publish_post_task.delay(post.id, platform_status.social_account.id)
            count += 1

    return f"Queued {count} publish tasks for due scheduled posts."



@shared_task
def sync_external_posts_task():
    """প্রতি 30 মিনিটে Meta থেকে posts auto-sync করা"""
    from .models import ExternalPost
    from django.utils.dateparse import parse_datetime

    accounts = SocialAccount.objects.filter(
        status='connected',
        platform__in=['facebook', 'instagram']
    )

    total_synced = 0

    for account in accounts:
        try:
            from integrations.facebook_adapter import FacebookAdapter
            adapter = FacebookAdapter()
            page_token, error = adapter.get_page_token(account)

            if error:
                continue

            if account.platform == 'facebook':
                page_id = account.platform_account_id
                res = requests.get(
                    f'https://graph.facebook.com/v22.0/{page_id}/published_posts',
                    params={
                        'access_token': page_token,
                        'fields': 'id,message,full_picture,created_time,permalink_url,'
                                  'likes.summary(true),comments.summary(true),shares',
                        'limit': 50
                    },
                    timeout=15
                ).json()

                for p in res.get('data', []):
                    ExternalPost.objects.update_or_create(
                        social_account=account,
                        external_post_id=p['id'],
                        defaults={
                            'platform': 'facebook',
                            'content': p.get('message', ''),
                            'media_url': p.get('full_picture', ''),
                            'permalink_url': p.get('permalink_url', ''),
                            'likes': p.get('likes', {}).get('summary', {}).get('total_count', 0),
                            'comments': p.get('comments', {}).get('summary', {}).get('total_count', 0),
                            'shares': p.get('shares', {}).get('count', 0),
                            'posted_at': parse_datetime(p['created_time']) if p.get('created_time') else None,
                        }
                    )
                    total_synced += 1

            elif account.platform == 'instagram':
                page_id = account.platform_account_id
                ig_res = requests.get(
                    f'https://graph.facebook.com/v22.0/{page_id}/media',
                    params={
                        'access_token': page_token,
                        'fields': 'id,caption,media_type,media_url,thumbnail_url,timestamp,like_count,comments_count,permalink',
                        'limit': 50
                    },
                    timeout=15
                ).json()

                for p in ig_res.get('data', []):
                    ExternalPost.objects.update_or_create(
                        social_account=account,
                        external_post_id=p['id'],
                        defaults={
                            'platform': 'instagram',
                            'content': p.get('caption', ''),
                            'media_url': p.get('media_url') or p.get('thumbnail_url', ''),
                            'media_type': p.get('media_type', ''),
                            'permalink_url': p.get('permalink', ''),
                            'likes': p.get('like_count', 0),
                            'comments': p.get('comments_count', 0),
                            'posted_at': parse_datetime(p['timestamp']) if p.get('timestamp') else None,
                        }
                    )
                    total_synced += 1

        except Exception as e:
            print(f"[Sync Error] {account.account_name}: {e}")

    return f"Auto-synced {total_synced} external posts."