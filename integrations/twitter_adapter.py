import time
import requests
from .base import BaseSocialAdapter


class TwitterAdapter(BaseSocialAdapter):
    API_URL = "https://api.twitter.com/2/tweets"

    def publish_post(self, post) -> dict:
        if self._is_mock():
            time.sleep(1)
            return {'status': 'success', 'platform_post_id': f"mock_x_{post.id}"}

        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
        }

        try:
            res = requests.post(
                self.API_URL,
                json={"text": post.content},
                headers=headers,
                timeout=15
            )
            data = res.json()

            if res.status_code == 201 and 'data' in data:
                return {'status': 'success', 'platform_post_id': data['data']['id']}

            error_msg = data.get('detail', data.get('title', 'Unknown X API error'))
            return {'status': 'failed', 'error_message': error_msg}

        except requests.RequestException as e:
            return {'status': 'failed', 'error_message': f"X API timeout: {e}"}