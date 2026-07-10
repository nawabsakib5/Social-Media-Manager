import time
import requests
from .base import BaseSocialAdapter

VIDEO_EXTENSIONS = ('.mp4', '.mov', '.avi', '.mkv')


class FacebookAdapter(BaseSocialAdapter):
    API_VERSION = "v21.0"
    BASE_URL = f"https://graph.facebook.com/v21.0"

    def get_page_token(self) -> str:
        """Exchange system user token for page access token."""
        url = f"{self.BASE_URL}/me/accounts"
        res = requests.get(url, params={'access_token': self.access_token}, timeout=15)
        data = res.json()
        page_id = self.social_account.platform_account_id
        for page in data.get('data', []):
            if page.get('id') == page_id:
                return page['access_token']
        # Fallback to system user token if page token not found
        return self.access_token

    def publish_post(self, post) -> dict:
        if self._is_mock():
            time.sleep(2)
            return {'status': 'success', 'platform_post_id': f"mock_fb_{post.id}"}

        page_id = self.social_account.platform_account_id
        page_token = self.get_page_token()

        try:
            if post.media_file:
                name = post.media_file.name.lower()
                if any(name.endswith(ext) for ext in VIDEO_EXTENSIONS):
                    return self._publish_video(post, page_id, page_token)
                return self._publish_photo(post, page_id, page_token)
            return self._publish_text(post, page_id, page_token)

        except requests.RequestException as e:
            return {'status': 'failed', 'error_message': f"Facebook connection timeout: {e}"}

    # --- Private helpers ---

    def _publish_text(self, post, page_id, token) -> dict:
        url = f"{self.BASE_URL}/{page_id}/feed"
        res = requests.post(url, data={'message': post.content, 'access_token': token}, timeout=15)
        return self._handle_response(res)

    def _publish_photo(self, post, page_id, token) -> dict:
        url = f"{self.BASE_URL}/{page_id}/photos"
        try:
            with post.media_file.open('rb') as img:
                res = requests.post(
                    url,
                    data={'message': post.content, 'access_token': token},
                    files={'source': img},
                    timeout=30
                )
            return self._handle_response(res)
        except Exception as e:
            return {'status': 'failed', 'error_message': f"Photo upload error: {e}"}

    def _publish_video(self, post, page_id, token) -> dict:
        url = f"{self.BASE_URL}/{page_id}/videos"
        try:
            with post.media_file.open('rb') as vid:
                res = requests.post(
                    url,
                    data={'description': post.content, 'access_token': token},
                    files={'source': vid},
                    timeout=60
                )
            return self._handle_response(res)
        except Exception as e:
            return {'status': 'failed', 'error_message': f"Video upload error: {e}"}

    def _handle_response(self, response) -> dict:
        try:
            data = response.json()
        except Exception:
            return {'status': 'failed', 'error_message': 'Invalid JSON from Facebook API'}

        if response.status_code == 200 and ('id' in data or 'post_id' in data):
            return {
                'status': 'success',
                'platform_post_id': data.get('post_id') or data.get('id')
            }
        error_msg = data.get('error', {}).get('message', 'Unknown Facebook API error')
        return {'status': 'failed', 'error_message': error_msg}