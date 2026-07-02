from celery import shared_task
from .models import Post
from integrations import get_social_adapter

@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def publish_post_task(self, post_id):
    try:
        post = Post.objects.get(id=post_id)
        social_account = post.social_account
        
        print(f"Task Started: Preparing connection to {social_account.platform} for Post ID {post_id}")
        
        # 1. Resolve and instantiate the correct platform adapter dynamically
        adapter = get_social_adapter(social_account)
        
        # 2. Execute publishing sequence
        result = adapter.publish_post(post)
        
        # 3. Handle success or failure states in the database
        if result['status'] == 'success':
            post.status = 'published'
            post.platform_post_id = result['platform_post_id']
            post.error_message = None
            post.save()
            print(f"Task Success: Post {post_id} published successfully to {social_account.platform}")
            return f"Post {post_id} Published"
        else:
            post.status = 'failed'
            post.error_message = result['error_message']
            post.save()
            print(f"Task Failed: Publishing post {post_id} failed with error: {result['error_message']}")
            
            # Retry automatically if it is a network-related failure
            if "connection network timeout" in result['error_message']:
                print(f"Network error detected. Retrying task for Post {post_id}...")
                self.retry(exc=Exception(result['error_message']))
                
            return f"Failed: {result['error_message']}"
            
    except Post.DoesNotExist:
        print(f"Task Aborted: Post with ID {post_id} not found.")
        return "Post Not Found"
    except Exception as e:
        print(f"Task Crashed: Unexpected exception occurred: {str(e)}")
        # Safeguard fallback to mark post as failed in database
        try:
            post = Post.objects.get(id=post_id)
            post.status = 'failed'
            post.error_message = str(e)
            post.save()
        except:
            pass
        return f"Error: {str(e)}"