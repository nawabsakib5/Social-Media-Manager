import time
import requests
from .base import BaseSocialAdapter


class InstagramAdapter(BaseSocialAdapter):
    API_VERSION = "v22.0"
    BASE_URL = "https://graph.facebook.com/v22.0"

    def __init__(self, social_account=None):
        super().__init__(social_account)

    def publish_post(self, post, platform_status):
        if self._is_mock():
            time.sleep(2)
            return True, f"mock_ig_{post.id}"

        if not post.media_file:
            return False, "Instagram requires an image or video."

        social_account = platform_status.social_account
        ig_id = social_account.platform_account_id
        
        from .facebook_adapter import FacebookAdapter
        adapter = FacebookAdapter()
        token, error = adapter.get_page_token(social_account)
        
        if error:
            return False, error

        public_url = self._get_public_url(post)

        try:
            if self._is_video(post):
                return self._publish_video(post, ig_id, token, public_url)
            else:
                return self._publish_photo(post, ig_id, token, public_url)

        except requests.RequestException as e:
            return False, f"Instagram API timeout: {e}"
        except Exception as e:
            return False, str(e)

    def _is_video(self, post) -> bool:
        url = post.media_file.url
        if '/video/upload/' in url:
            return True
        if '/image/upload/' in url:
            return False
        name = post.media_file.name.lower()
        return any(name.endswith(ext) for ext in ('.mp4', '.mov', '.avi', '.webm', '.mkv'))

    def _get_public_url(self, post) -> str:
        url = post.media_file.url
        if url.startswith('https://res.cloudinary.com') or url.startswith('http://res.cloudinary.com'):
            return url
        from django.conf import settings
        return f"{settings.SITE_URL}{url}"

    def _publish_photo(self, post, ig_id, token, public_url):
        try:
            container_id = self._create_container(ig_id, token, {
                'image_url': public_url,
                'caption': post.content or '',
                'access_token': token,
            })
            return self._publish_container(ig_id, token, container_id)
        except Exception as e:
            return False, str(e)

    def _publish_video(self, post, ig_id, token, public_url):
        try:
            container_id = self._create_container(ig_id, token, {
                'video_url': public_url,
                'caption': post.content or '',
                'media_type': 'REELS',
                'access_token': token,
            })
            
            time.sleep(5)
            return self._publish_container(ig_id, token, container_id)
        except Exception as e:
            return False, str(e)

    def _create_container(self, ig_id, token, payload) -> str:
        url = f"{self.BASE_URL}/{ig_id}/media"
        res = requests.post(url, data=payload, timeout=60)
        data = res.json()
        if 'id' in data:
            return data['id']
        error = data.get('error', {}).get('message', 'Unknown error')
        raise ValueError(f"Container creation failed: {error}")

    def _publish_container(self, ig_id, token, creation_id):
        url = f"{self.BASE_URL}/{ig_id}/media_publish"
        res = requests.post(
            url,
            data={'creation_id': creation_id, 'access_token': token},
            timeout=30
        )
        data = res.json()
        if 'id' in data:
            return True, data['id']
        error = data.get('error', {}).get('message', 'Publish failed')
        return False, error

    
    def delete_post(self, post, platform_status):
        
        return False, "Meta API restriction: Instagram posts cannot be deleted via third-party APIs. Please delete manually."

    def update_post(self, post, platform_status, new_text):
        
        return False, "Meta API restriction: Instagram captions cannot be updated via third-party APIs. Please edit manually."