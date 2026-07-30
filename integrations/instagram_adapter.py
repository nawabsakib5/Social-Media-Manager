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

        if not ig_id:
            return False, "No Instagram Business account connected. Please reconnect via Facebook OAuth."

        from .facebook_adapter import FacebookAdapter
        adapter = FacebookAdapter()
        token, error = adapter.get_page_token(social_account)

        if error:
            return False, error

        # media_type field থেকে video/image detect করা হচ্ছে (সবচেয়ে reliable)
        # তারপর Cloudinary /auto/upload/ URL কে সঠিক type-এ fix করা হচ্ছে
        public_url = self._get_fixed_url(post)

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
        # ১. model-এর media_type field সবচেয়ে reliable (upload সময় set হয়)
        model_type = getattr(post, 'media_type', None)
        if model_type == 'video':
            return True
        if model_type == 'image':
            return False

        # ২. Cloudinary URL-এ /video/upload/ বা /image/upload/ থাকলে সেটা দেখা
        url = post.media_file.url
        if '/video/upload/' in url:
            return True
        if '/image/upload/' in url:
            return False

        # ৩. filename extension দেখা (fallback)
        name = post.media_file.name.lower()
        return any(name.endswith(ext) for ext in ('.mp4', '.mov', '.avi', '.webm', '.mkv'))

    def _get_fixed_url(self, post) -> str:
    
        url = post.media_file.url
        is_video = self._is_video(post)

        if is_video:
            
            if '/auto/upload/' in url:
                url = url.replace('/auto/upload/', '/video/upload/')
            
            if 'res.cloudinary.com' in url and not url.lower().endswith('.mp4'):
                url = url.replace('/video/upload/', '/video/upload/f_mp4/')
        else:
            
            if '/auto/upload/' in url:
                url = url.replace('/auto/upload/', '/image/upload/')
            
            if 'res.cloudinary.com' in url and not any(
                url.lower().endswith(ext) for ext in ('.jpg', '.jpeg', '.png')
            ):
                url = url.replace('/image/upload/', '/image/upload/f_jpg/')

        return url

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
            # ভিডিও processing-এর জন্য Instagram-কে সময় দেওয়া হচ্ছে
            time.sleep(10)
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