import time
import requests
from .base import BaseSocialAdapter

class TwitterAdapter(BaseSocialAdapter):
    def publish_post(self, post) -> dict:
        if self.access_token.startswith("mock_"):
            time.sleep(1)
            return {
                'status': 'success',
                'platform_post_id': f"mock_x_tweet_{post.id}"
            }
        
        # X API v2 (POST /2/tweets)
        url = "https://api.twitter.com/2/tweets"
        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json"
        }
        payload = {
            "text": post.content
        }
        
        try:
            response = requests.post(url, json=payload, headers=headers, timeout=15)
            response_data = response.json()
            
            if response.status_code == 201 and 'data' in response_data:
                return {
                    'status': 'success',
                    'platform_post_id': response_data['data']['id']
                }
            else:
                error_msg = response_data.get('detail', 'Unknown X (Twitter) API Error')
                return {
                    'status': 'failed',
                    'error_message': error_msg
                }
        except requests.RequestException as e:
            return {
                'status': 'failed',
                'error_message': f"X API network timeout: {str(e)}"
            }