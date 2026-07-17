import requests
from django.conf import settings
from .base import BaseSocialAdapter


class FacebookAdapter(BaseSocialAdapter):
    platform = 'facebook'
    
    def __init__(self, social_account=None):
        super().__init__(social_account)
    
    def get_page_token(self, social_account):
        """
        Get page access token for a specific page.
        Since we store the Never-Expiring Page Token directly in the model,
        we can safely and directly return the stored token.
        """
        stored_token = social_account.access_token if hasattr(social_account, 'access_token') else None
        
        if stored_token:
            return stored_token, None
            
        return None, "No access token available. Please reconnect the account."
    
    def publish_post(self, post, platform_status):
        """Publish post to Facebook page"""
        social_account = platform_status.social_account
        page_token, error = self.get_page_token(social_account)
        
        if error:
            return False, error
        
        page_id = social_account.platform_account_id
        url = f"https://graph.facebook.com/v22.0/{page_id}/feed"
        
        # আপনার মডেল অনুযায়ী post.content ব্যবহার করা হয়েছে
        post_content = getattr(post, 'content', '') or getattr(post, 'text_content', '')
        
        data = {
            'access_token': page_token,
            'message': post_content or ''
        }
        
        # আপনার মডেল অনুযায়ী post.media_file ব্যবহার করা হয়েছে
        media_file = getattr(post, 'media_file', None) or getattr(post, 'media', None)
        
        # মিডিয়া আপলোড হ্যান্ডেল করা হচ্ছে
        if media_file:
            media_id = self.upload_media(post, page_token)
            if media_id:
                # মেটা গ্রাফ এপিআই-এর নিয়ম অনুযায়ী attached_media-তে অ্যারে ব্র্যাকেট [] যুক্ত করা হয়েছে
                data['attached_media'] = f'[{{"media_fbid":"{media_id}"}}]'
        
        try:
            response = requests.post(url, data=data, timeout=30)
            
            if response.status_code == 200:
                result = response.json()
                return True, result.get('id')
            
            error_msg = response.json().get('error', {}).get('message', response.text)
            return False, error_msg
            
        except requests.RequestException as e:
            return False, str(e)
    
    def upload_media(self, post, page_token):
        """Upload media to Facebook"""
        media_file = getattr(post, 'media_file', None) or getattr(post, 'media', None)
        if not media_file:
            return None
        
        media_url = media_file.url
        media_url_lower = media_url.lower()
        is_video = any(ext in media_url_lower for ext in ['.mp4', '.mov', '.avi', '.webm'])
        
        try:
            if not is_video:
                url = "https://graph.facebook.com/v22.0/me/photos"
                data = {
                    'access_token': page_token,
                    'url': media_url,
                    'published': False
                }
                response = requests.post(url, data=data, timeout=30)
            else:
                url = "https://graph.facebook.com/v22.0/me/videos"
                post_content = getattr(post, 'content', '') or getattr(post, 'text_content', '')
                post_title = getattr(post, 'title', 'Social Media Post')
                
                data = {
                    'access_token': page_token,
                    'title': post_title,
                    'description': post_content or ''
                }
                data['file_url'] = media_url
                response = requests.post(url, data=data, timeout=60)
            
            if response.status_code == 200:
                result = response.json()
                return result.get('id')
            
            return None
            
        except requests.RequestException:
            return None
    
    def delete_post(self, post, platform_status):
        """Delete post from Facebook"""
        page_token, error = self.get_page_token(platform_status.social_account)
        if error:
            return False, error
        
        post_id = platform_status.platform_post_id
        url = f"https://graph.facebook.com/v22.0/{post_id}"
        params = {'access_token': page_token}
        
        try:
            response = requests.delete(url, params=params, timeout=15)
            if response.status_code == 200:
                return True, None
            error_msg = response.json().get('error', {}).get('message', response.text)
            return False, error_msg
        except requests.RequestException as e:
            return False, str(e)
    
    def update_post(self, post, platform_status, new_text):
        """Update post caption on Facebook"""
        page_token, error = self.get_page_token(platform_status.social_account)
        if error:
            return False, error
        
        post_id = platform_status.platform_post_id
        url = f"https://graph.facebook.com/v22.0/{post_id}"
        data = {
            'access_token': page_token,
            'message': new_text
        }
        
        try:
            response = requests.post(url, data=data, timeout=15)
            if response.status_code == 200:
                return True, None
            error_msg = response.json().get('error', {}).get('message', response.text)
            return False, error_msg
        except requests.RequestException as e:
            return False, str(e)