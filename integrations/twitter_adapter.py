import time
import requests
from .base import BaseSocialAdapter


class TwitterAdapter(BaseSocialAdapter):
    API_URL = "https://api.twitter.com/2/tweets"

    def __init__(self, social_account=None):
        super().__init__(social_account)

    def publish_post(self, post, platform_status):
        """Publish a tweet to Twitter/X using OAuth 2.0 User Access Token"""
        if self._is_mock():
            time.sleep(1)
            return True, f"mock_x_{post.id}"

        social_account = platform_status.social_account
        token = social_account.access_token 

        if not token:
            return False, "Twitter access token not found. Please reconnect account."

        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }

        
        post_content = getattr(post, 'content', '') or getattr(post, 'text_content', '')

        try:
            res = requests.post(
                self.API_URL,
                json={"text": post_content},
                headers=headers,
                timeout=15
            )
            data = res.json()

            
            if res.status_code == 201 and 'data' in data:
                return True, data['data']['id']

            error_msg = data.get('detail', data.get('title', 'Unknown X API error'))
            return False, error_msg

        except requests.RequestException as e:
            return False, f"X API timeout: {e}"
        except Exception as e:
            return False, str(e)

    def delete_post(self, post, platform_status):
        """Delete a tweet from Twitter/X using the API v2 delete endpoint"""
        social_account = platform_status.social_account
        token = social_account.access_token
        tweet_id = platform_status.platform_post_id

        if not token or not tweet_id:
            return False, "Missing Twitter credentials or Tweet ID."

        headers = {
            "Authorization": f"Bearer {token}",
        }

        try:
            
            url = f"https://api.twitter.com/2/tweets/{tweet_id}"
            res = requests.delete(url, headers=headers, timeout=15)
            
            if res.status_code == 200:
                data = res.json()
                if data.get('data', {}).get('deleted'):
                    return True, None
                
            error_msg = res.json().get('detail', 'X delete failed')
            return False, error_msg
        except Exception as e:
            return False, str(e)

    def update_post(self, post, platform_status, new_text):
        """API Caption edit is not supported by Twitter API v2, must be manual"""
        return False, "X API restriction: Tweets cannot be edited via third-party APIs. Please edit manually on X."