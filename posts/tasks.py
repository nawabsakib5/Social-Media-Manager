from celery import shared_task
from django.utils import timezone
from .models import Post
from integrations import get_social_adapter


@shared_task
def check_and_publish_scheduled_posts():
    now = timezone.now()
    due_posts = Post.objects.filter(
        status='scheduled',
        scheduled_time__lte=now
    )
    count = 0
    for post in due_posts:
        publish_post_task.delay(post.id)
        count += 1
    print(f"[Beat] {count} টা post queue-এ পাঠানো হয়েছে")
    return f"Queued {count} posts"


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def publish_post_task(self, post_id):
    try:
        post = Post.objects.get(id=post_id)
        social_account = post.social_account
        print(f"Task Started: {social_account.platform} — Post ID {post_id}")

        adapter = get_social_adapter(social_account)
        result = adapter.publish_post(post)

        if result['status'] == 'success':
            platform_post_id = result.get('platform_post_id', '')
            if not platform_post_id or str(platform_post_id).startswith('mock_'):
                post.status = 'failed'
                post.error_message = 'Mock token — real access token দিন'
                post.save()
                return "Failed: mock token"

            post.status = 'published'
            post.platform_post_id = platform_post_id
            post.error_message = None
            post.save()
            print(f"Task Success: Post {post_id} → ID: {platform_post_id}")
            return f"Published: {platform_post_id}"
        else:
            error_msg = result.get('error_message', 'Unknown error')
            post.status = 'failed'
            post.error_message = error_msg
            post.save()
            if "connection network timeout" in error_msg:
                self.retry(exc=Exception(error_msg))
            return f"Failed: {error_msg}"

    except Post.DoesNotExist:
        return "Post Not Found"
    except Exception as e:
        try:
            post = Post.objects.get(id=post_id)
            post.status = 'failed'
            post.error_message = str(e)
            post.save()
        except Exception:
            pass
        return f"Error: {str(e)}"