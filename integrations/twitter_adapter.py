# integrations/twitter_adapter.py
import time
import requests
import base64
from django.conf import settings
from .base import BaseSocialAdapter


class TwitterAdapter(BaseSocialAdapter):
    API_URL = "https://api.twitter.com/2/tweets"

    def __init__(self, social_account=None):
        super().__init__(social_account)

    def refresh_twitter_token(self, social_account):
        """টুইটার ওআউথ ২.০ টোকেন ২ ঘণ্টা পর এক্সপায়ার হলে ব্যাকএন্ডে স্বয়ংক্রিয়ভাবে সেটি রিফ্রেশ করা"""
        refresh_token = social_account.refresh_token if hasattr(social_account, 'refresh_token') else None
        
        if not refresh_token:
            return None, "No refresh token found. Please reconnect account."
            
        token_url = "https://api.twitter.com/2/oauth2/token"
        client_id = getattr(settings, 'TWITTER_CLIENT_ID', '')
        client_secret = getattr(settings, 'TWITTER_CLIENT_SECRET', '')
        
        auth_str = f"{client_id}:{client_secret}"
        b64_auth = base64.b64encode(auth_str.encode('utf-8')).decode('utf-8')
        
        headers = {
            'Authorization': f'Basic {b64_auth}',
            'Content-Type': 'application/x-www-form-urlencoded',
        }
        
        payload = {
            'grant_type': 'refresh_token',
            'refresh_token': refresh_token,
            'client_id': client_id,
        }
        
        try:
            res = requests.post(token_url, headers=headers, data=payload, timeout=15)
            token_data = res.json()
            
            if 'access_token' in token_data:
                social_account.access_token = token_data['access_token']
                if 'refresh_token' in token_data:
                    social_account.refresh_token = token_data['refresh_token']
                social_account.save()
                return token_data['access_token'], None
                
            return None, token_data.get('error_description', 'Token refresh failed.')
        except Exception as e:
            return None, str(e)

    def publish_post(self, post, platform_status):
        """Publish a tweet (Supports both text and Cloudinary Images) with auto token refresh"""
        if self._is_mock():
            time.sleep(1)
            return True, f"mock_x_{post.id}"

        social_account = platform_status.social_account
        token = social_account.access_token

        if not token:
            return False, "Twitter access token not found. Please reconnect account."

        post_content = getattr(post, 'content', '') or getattr(post, 'text_content', '')

        # প্রথমবার টুইট পোস্ট করার চেষ্টা
        success, res_val = self._send_tweet_request(post, post_content, token)
        
        # টোকেন মেয়াদোত্তীর্ণ হওয়ার কারণে "Unauthorized (401)" এরর দিলে অটো-রিফ্রেশ করা হচ্ছে
        if not success and ("unauthorized" in str(res_val).lower() or "401" in str(res_val)):
            print(f"[Twitter Refresh] Token expired for @{social_account.account_username}. Attempting auto-refresh...")
            new_token, refresh_error = self.refresh_twitter_token(social_account)
            
            if refresh_error:
                return False, f"Twitter session expired and refresh failed: {refresh_error}"
                
            # নতুন অ্যাক্টিভ টোকেন দিয়ে দ্বিতীয়বার পোস্ট করার চেষ্টা (১00% সাকসেস হবে)
            return self._send_tweet_request(post, post_content, new_token)
            
        return success, res_val

    def _send_tweet_request(self, post, content, token):
        """টুইটার এপিআই-তে রিকোয়েস্ট পাঠানোর সাহায্যকারী মেথড (ইমেজ আপলোড সাপোর্টসহ)"""
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }
        
        payload = {"text": content or ""}
        media_file = getattr(post, 'media_file', None) or getattr(post, 'media', None)
        
        # যদি পোস্টে ছবি থাকে, তবে ২-ধাপের মিডিয়া আপলোড মেথডটি রান করা হচ্ছে
        if media_file:
            media_id = self._upload_media_to_twitter(media_file, token)
            if media_id:
                payload["media"] = {
                    "media_ids": [str(media_id)] # টুইটার এপিআই ২.০ স্ট্রাকচার অনুযায়ী মিডিয়া আইডি অ্যাটাচ
                }

        try:
            res = requests.post(
                self.API_URL,
                json=payload,
                headers=headers,
                timeout=15
            )
            data = res.json()
            if res.status_code == 201 and 'data' in data:
                return True, data['data']['id']
                
            error_msg = data.get('detail', data.get('title', 'Unknown X API error'))
            return False, error_msg
        except Exception as e:
            return False, str(e)

    def _upload_media_to_twitter(self, media_file, token):
        """টুইটার আপলোড ১.১ এপিআই ব্যবহার করে ক্লাউডিনারি ইমেজ বাইনারি টুইটারে আপলোড করা"""
        try:
            # ক্লাউডিনারি ইউআরএল থেকে ইমেজের বাইনারি কন্টেন্ট ডাউনলোড করা হচ্ছে
            img_res = requests.get(media_file.url, timeout=15)
            if img_res.status_code != 200:
                return None
                
            upload_url = "https://upload.twitter.com/1.1/media/upload.json"
            headers = {
                "Authorization": f"Bearer {token}",
            }
            # ইমেজ বাইনারি ফাইল অবজেক্ট
            files = {
                'media': ('image.jpg', img_res.content, 'image/jpeg')
            }
            
            # টুইটারে ইমেজ আপলোড
            res = requests.post(upload_url, headers=headers, files=files, timeout=30)
            if res.status_code in [200, 201]:
                return res.json().get('media_id_string')
            return None
        except Exception as e:
            print(f"X Media Upload Error: {e}")
            return None

    def delete_post(self, post, platform_status):
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
        return False, "X API restriction: Tweets cannot be edited via third-party APIs. Please edit manually on X."