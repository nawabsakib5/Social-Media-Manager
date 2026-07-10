import time
import requests
from django.conf import settings
from .base import BaseSocialAdapter

VIDEO_EXTENSIONS = ('.mp4', '.mov', '.avi')


class InstagramAdapter(BaseSocialAdapter):
    API_VERSION = "v21.0"
    BASE_URL = "https://graph.facebook.com/v21.0"

    def publish_post(self, post) -> dict:
        if self._is_mock():
            time.sleep(2)
            return {'status': 'success', 'platform_post_id': f"mock_ig_{post.id}"}

        if not post.media_file:
            return {'status': 'failed', 'error_message': "Instagram requires an image or video."}

        ig_id = self.social_account.platform_account_id
        token = self.access_token

        # Build public Cloudinary URL
        public_url = self._get_public_url(post)

        try:
            name = post.media_file.name.lower()
            if any(name.endswith(ext) for ext in VIDEO_EXTENSIONS):
                return self._publish_video(post, ig_id, token, public_url)
            return self._publish_photo(post, ig_id, token, public_url)

        except requests.RequestException as e:
            return {'status': 'failed', 'error_message': f"Instagram API timeout: {e}"}

    def _get_public_url(self, post) -> str:
        """
        Return Cloudinary URL if available, otherwise fall back to SITE_URL.
        Cloudinary storage returns an absolute URL directly via post.media_file.url.
        """
        url = post.media_file.url
        if url.startswith('http'):
            return url  # Already a Cloudinary absolute URL
        return f"{settings.SITE_URL}{url}"

    # --- Private helpers ---

    def _publish_photo(self, post, ig_id, token, public_url) -> dict:
        container_id = self._create_container(ig_id, token, {
            'image_url': public_url,
            'caption': post.content,
            'access_token': token,
        })
        if not container_id:
            return {'status': 'failed', 'error_message': 'Instagram photo container creation failed'}
        return self._publish_container(ig_id, token, container_id)

    def _publish_video(self, post, ig_id, token, public_url) -> dict:
        container_id = self._create_container(ig_id, token, {
            'video_url': public_url,
            'caption': post.content,
            'media_type': 'REELS',
            'access_token': token,
        })
        if not container_id:
            return {'status': 'failed', 'error_message': 'Instagram video container creation failed'}
        return self._publish_container(ig_id, token, container_id)

    def _create_container(self, ig_id, token, payload) -> str | None:
        """Create media container and return its ID, or None on failure."""
        url = f"{self.BASE_URL}/{ig_id}/media"
        res = requests.post(url, data=payload, timeout=60)
        data = res.json()
        if 'id' in data:
            return data['id']
        error = data.get('error', {}).get('message', 'Unknown error')
        raise ValueError(f"Container creation failed: {error}")

    def _publish_container(self, ig_id, token, creation_id) -> dict:
        url = f"{self.BASE_URL}/{ig_id}/media_publish"
        res = requests.post(url, data={'creation_id': creation_id, 'access_token': token}, timeout=30)
        data = res.json()
        if 'id' in data:
            return {'status': 'success', 'platform_post_id': data['id']}
        error = data.get('error', {}).get('message', 'Publish failed')
        return {'status': 'failed', 'error_message': error}