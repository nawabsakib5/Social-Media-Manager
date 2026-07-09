import time
import requests
from .base import BaseSocialAdapter


class FacebookAdapter(BaseSocialAdapter):
    API_VERSION = "v21.0"

    def get_page_token(self):
        """System User token থেকে Page Access Token নেওয়া"""
        url = f"https://graph.facebook.com/{self.API_VERSION}/me/accounts"
        res = requests.get(url, params={'access_token': self.access_token}, timeout=15)
        data = res.json()
        page_id = self.social_account.platform_account_id
        for page in data.get('data', []):
            if page.get('id') == page_id:
                return page.get('access_token')
        return self.access_token

    def publish_post(self, post) -> dict:
        if self.access_token.startswith("mock_"):
            time.sleep(2)
            return {
                'status': 'success',
                'platform_post_id': f"mock_fb_post_{post.id}"
            }

        page_id = self.social_account.platform_account_id
        page_token = self.get_page_token()

        try:
            if post.media_file:
                file_name = post.media_file.name.lower()
                if file_name.endswith(('.mp4', '.mov', '.avi', '.mkv')):
                    return self._publish_video(post, page_id, page_token)
                else:
                    return self._publish_photo(post, page_id, page_token)
            else:
                return self._publish_text(post, page_id, page_token)

        except requests.RequestException as e:
            return {
                'status': 'failed',
                'error_message': f"Meta connection network timeout: {str(e)}"
            }

    def _publish_text(self, post, page_id, token) -> dict:
        url = f"https://graph.facebook.com/{self.API_VERSION}/{page_id}/feed"
        payload = {'message': post.content, 'access_token': token}
        response = requests.post(url, data=payload, timeout=15)
        return self._handle_response(response)

    def _publish_photo(self, post, page_id, token) -> dict:
        url = f"https://graph.facebook.com/{self.API_VERSION}/{page_id}/photos"
        try:
            with post.media_file.open('rb') as img:
                files = {'source': img}
                payload = {'message': post.content, 'access_token': token}
                response = requests.post(url, data=payload, files=files, timeout=30)
            return self._handle_response(response)
        except Exception as e:
            return {'status': 'failed', 'error_message': f"Photo upload error: {str(e)}"}

    def _publish_video(self, post, page_id, token) -> dict:
        url = f"https://graph.facebook.com/{self.API_VERSION}/{page_id}/videos"
        try:
            with post.media_file.open('rb') as vid:
                files = {'source': vid}
                payload = {'description': post.content, 'access_token': token}
                response = requests.post(url, data=payload, files=files, timeout=60)
            return self._handle_response(response)
        except Exception as e:
            return {'status': 'failed', 'error_message': f"Video upload error: {str(e)}"}

    def _handle_response(self, response) -> dict:
        try:
            data = response.json()
        except Exception:
            return {'status': 'failed', 'error_message': 'Invalid JSON response'}

        if response.status_code == 200 and ('id' in data or 'post_id' in data):
            return {
                'status': 'success',
                'platform_post_id': data.get('post_id') or data.get('id')
            }
        else:
            error_msg = data.get('error', {}).get('message', 'Unknown Facebook API Error')
            return {'status': 'failed', 'error_message': error_msg}