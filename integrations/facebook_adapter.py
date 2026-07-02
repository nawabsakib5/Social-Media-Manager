import time
import requests
from .base import BaseSocialAdapter

class FacebookAdapter(BaseSocialAdapter):
    def publish_post(self, post) -> dict:
        # Check if we should execute Mock flow
        if self.access_token.startswith("mock_"):
            time.sleep(2)  # Simulates API call processing latency
            return {
                'status': 'success',
                'platform_post_id': f"mock_fb_post_{post.id}"
            }
        
        # Real Meta Graph API publishing execution
        url = f"https://graph.facebook.com/v20.0/{self.social_account.platform_account_id}/feed"
        payload = {
            'message': post.content,
            'access_token': self.access_token
        }
        
        try:
            response = requests.post(url, data=payload, timeout=15)
            response_data = response.json()
            
            if response.status_code == 200 and 'id' in response_data:
                return {
                    'status': 'success',
                    'platform_post_id': response_data['id']
                }
            else:
                error_msg = response_data.get('error', {}).get('message', 'Unknown Facebook API Error')
                return {
                    'status': 'failed',
                    'error_message': error_msg
                }
        except requests.RequestException as e:
            return {
                'status': 'failed',
                'error_message': f"Meta connection network timeout: {str(e)}"
            }