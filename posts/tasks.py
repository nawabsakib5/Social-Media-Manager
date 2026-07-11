from celery import shared_task
from django.utils import timezone
from .models import Post, PostPlatformStatus
from integrations import get_social_adapter


@shared_task
def check_and_publish_scheduled_posts():
    from django.utils import timezone
    now = timezone.now()
    
    due_posts = Post.objects.filter(
        status='scheduled',
        scheduled_time__lte=now
    ).prefetch_related('social_accounts', 'platform_statuses')
    
    print(f"[DEBUG] Now: {now}")
    print(f"[DEBUG] Due posts count: {due_posts.count()}")
    
    fired = 0
    for post in due_posts:
        print(f"[DEBUG] Post {post.id} scheduled_time: {post.scheduled_time}")
        for account in post.social_accounts.all():
            already_handled = post.platform_statuses.filter(
                social_account=account,
                status__in=['published', 'processing']
            ).exists()
            print(f"[DEBUG] Account {account.id} already_handled: {already_handled}")
            if not already_handled:
                publish_post_task.delay(post.id, account.id)
                fired += 1

    return f"Queued {fired} publish tasks for due scheduled posts"


    

@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def publish_post_task(self, post_id, account_id):
    """
    Publishes a single post to a single social account.
    Updates PostPlatformStatus accordingly.
    For multi-platform posting, this task is fired
    separately for each selected account.
    """
    from social_accounts.models import SocialAccount

    # --- Fetch objects ---
    try:
        post = Post.objects.get(id=post_id)
    except Post.DoesNotExist:
        return f"Post {post_id} not found — skipping"

    try:
        account = SocialAccount.objects.get(id=account_id)
    except SocialAccount.DoesNotExist:
        return f"SocialAccount {account_id} not found — skipping"

    # --- Get or create platform status record ---
    status_obj, _ = PostPlatformStatus.objects.get_or_create(
        post=post,
        social_account=account,
        defaults={'status': 'scheduled'}
    )

    # Mark as processing so Beat doesn't re-queue it
    status_obj.status = 'processing'
    status_obj.error_message = None
    status_obj.save(update_fields=['status', 'error_message'])

    # --- Publish ---
    try:
        adapter = get_social_adapter(account)
        result = adapter.publish_post(post)

        if result['status'] == 'success':
            platform_post_id = result.get('platform_post_id', '')

            if not platform_post_id or str(platform_post_id).startswith('mock_'):
                status_obj.status = 'failed'
                status_obj.error_message = 'Mock token detected — provide a real access token'
                status_obj.save(update_fields=['status', 'error_message'])
                return f"Failed (mock token): post {post_id} → {account.platform}"

            status_obj.status = 'published'
            status_obj.platform_post_id = platform_post_id
            status_obj.error_message = None
            status_obj.published_at = timezone.now()
            status_obj.save(update_fields=['status', 'platform_post_id', 'error_message', 'published_at'])

            # Mark Post itself as published if all platforms are done
            all_statuses = post.platform_statuses.values_list('status', flat=True)
            if all(s == 'published' for s in all_statuses):
                post.status = 'published'
                post.save(update_fields=['status'])

            return f"Published: post {post_id} → {account.platform} (ID: {platform_post_id})"

        else:
            error_msg = result.get('error_message', 'Unknown error')
            status_obj.status = 'failed'
            status_obj.error_message = error_msg
            status_obj.save(update_fields=['status', 'error_message'])

            if 'connection' in error_msg.lower() or 'timeout' in error_msg.lower():
                raise self.retry(exc=Exception(error_msg), countdown=60 * (self.request.retries + 1))

            return f"Failed: post {post_id} → {account.platform}: {error_msg}"

    except Exception as e:
        status_obj.status = 'failed'
        status_obj.error_message = str(e)[:1000]
        status_obj.save(update_fields=['status', 'error_message'])

        try:
            raise self.retry(exc=e, countdown=60 * (self.request.retries + 1))
        except self.MaxRetriesExceededError:
            return f"Permanently failed: post {post_id} → {account.platform}: {e}"