# integrations/linkedin_adapter.py
import requests
from .base import BaseSocialAdapter


class LinkedinAdapter(BaseSocialAdapter):
    platform = 'linkedin'

    def __init__(self, social_account=None):
        super().__init__(social_account)

    def get_page_token(self, social_account):
        """Get LinkedIn access token (OIDC format)"""
        stored_token = social_account.access_token if hasattr(social_account, 'access_token') else None
        if stored_token:
            return stored_token, None
        return None, "No access token available. Please reconnect the account."

    def publish_post(self, post, platform_status):
        """Publish a post (share) to a user's LinkedIn profile feed using API v2"""
        social_account = platform_status.social_account
        token, error = self.get_page_token(social_account)

        if error:
            return False, error

        author_id = social_account.platform_account_id  # লিঙ্কডইনের ইউনিক মেম্বার URN আইডি
        if not author_id:
            return False, "LinkedIn Member ID (URN) not found. Please reconnect account."

        url = "https://api.linkedin.com/v2/posts"
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "X-Restli-Protocol-Version": "2.0.0"
        }

        # জ্যাঙ্গো মডেল অনুযায়ী post.content রিসিভ করা হচ্ছে
        post_content = getattr(post, 'content', '') or getattr(post, 'text_content', '')

        # লিঙ্কডইনের অফিশিয়াল এপিআই ২.০ রিকোয়েস্ট পে-লোড
        payload = {
            "author": f"urn:li:person:{author_id}",
            "commentary": post_content or "",
            "visibility": "PUBLIC",
            "distribution": {
                "feedDistribution": "MAIN_FEED",
                "targetEntities": []
            },
            "lifecycleState": "PUBLISHED"
        }

        try:
            res = requests.post(url, headers=headers, json=payload, timeout=20)
            
            # লিঙ্কডইন সফলভাবে পোস্ট তৈরি করলে ২০১ (Created) রিটার্ন করে
            if res.status_code in [200, 201]:
                post_id = res.headers.get('x-restli-id', res.json().get('id', ''))
                return True, post_id

            error_data = res.json() if res.text else {}
            error_msg = error_data.get('message', res.text)
            return False, f"LinkedIn API error: {error_msg}"

        except requests.RequestException as e:
            return False, f"Network error: {str(e)}"
        except Exception as e:
            return False, str(e)

    def delete_post(self, post, platform_status):
        """Delete post from LinkedIn"""
        social_account = platform_status.social_account
        token, error = self.get_page_token(social_account)
        if error:
            return False, error

        post_id = platform_status.platform_post_id
        url = f"https://api.linkedin.com/v2/posts/{post_id}"
        headers = {
            "Authorization": f"Bearer {token}",
            "X-Restli-Protocol-Version": "2.0.0"
        }

        try:
            res = requests.delete(url, headers=headers, timeout=15)
            if res.status_code == 204:  # লিঙ্কডইন নো-কন্টেন্ট কোড
                return True, None
            error_msg = res.json().get('message', 'LinkedIn delete failed')
            return False, error_msg
        except Exception as e:
            return False, str(e)

    def update_post(self, post, platform_status, new_text):
        """LinkedIn API does not support caption updates for standard member posts"""
        return False, "LinkedIn API restriction: Member shares cannot be updated via third-party APIs. Please edit manually on LinkedIn."