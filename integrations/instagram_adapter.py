import time
import requests
from django.conf import settings
from .base import BaseSocialAdapter


class InstagramAdapter(BaseSocialAdapter):
    API_VERSION = "v21.0"

    def publish_post(self, post) -> dict:
        if self.access_token.startswith("mock_"):
            time.sleep(2)
            return {
                'status': 'success',
                'platform_post_id': f"mock_ig_media_{post.id}"
            }

        if not post.media_file:
            return {
                'status': 'failed',
                'error_message': "Instagram requires an image or video file."
            }

        ig_id = self.social_account.platform_account_id
        token = self.access_token
        public_url = f"{settings.SITE_URL}{post.media_file.url}"
        file_name = post.media_file.name.lower()

        try:
            if file_name.endswith(('.mp4', '.mov', '.avi')):
                return self._publish_video(post, ig_id, token, public_url)
            else:
                return self._publish_photo(post, ig_id, token, public_url)
        except requests.RequestException as e:
            return {
                'status': 'failed',
                'error_message': f"Instagram API network timeout: {str(e)}"
            }

    def _publish_photo(self, post, ig_id, token, public_url) -> dict:
        container_url = f"https://graph.facebook.com/{self.API_VERSION}/{ig_id}/media"
        container_payload = {
            'image_url': public_url,
            'caption': post.content,
            'access_token': token
        }
        container_res = requests.post(container_url, data=container_payload, timeout=30)
        container_data = container_res.json()

        if 'id' not in container_data:
            error = container_data.get('error', {}).get('message', 'Container creation failed')
            return {'status': 'failed', 'error_message': error}

        return self._publish_container(ig_id, token, container_data['id'])

    def _publish_video(self, post, ig_id, token, public_url) -> dict:
        container_url = f"https://graph.facebook.com/{self.API_VERSION}/{ig_id}/media"
        container_payload = {
            'video_url': public_url,
            'caption': post.content,
            'media_type': 'REELS',
            'access_token': token
        }
        container_res = requests.post(container_url, data=container_payload, timeout=60)
        container_data = container_res.json()

        if 'id' not in container_data:
            error = container_data.get('error', {}).get('message', 'Video container failed')
            return {'status': 'failed', 'error_message': error}

        return self._publish_container(ig_id, token, container_data['id'])

    def _publish_container(self, ig_id, token, creation_id) -> dict:
        publish_url = f"https://graph.facebook.com/{self.API_VERSION}/{ig_id}/media_publish"
        publish_payload = {
            'creation_id': creation_id,
            'access_token': token
        }
        publish_res = requests.post(publish_url, data=publish_payload, timeout=30)
        publish_data = publish_res.json()

        if 'id' in publish_data:
            return {'status': 'success', 'platform_post_id': publish_data['id']}
        else:
            error = publish_data.get('error', {}).get('message', 'Publish failed')
            return {'status': 'failed', 'error_message': error}