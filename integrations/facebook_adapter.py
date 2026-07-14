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
        Handles both stored page tokens and fetching fresh ones.
        """
        # Try to get token from the account
        stored_token = social_account.get_token()
        
        if stored_token:
            # Verify token is still valid
            check_url = "https://graph.facebook.com/v21.0/me/accounts"
            try:
                check_resp = requests.get(
                    check_url, 
                    params={'access_token': stored_token},
                    timeout=10
                )
                
                if check_resp.status_code == 200:
                    pages = check_resp.json().get('data', [])
                    for page in pages:
                        if str(page.get('id')) == str(social_account.platform_account_id):
                            # Return the page-specific token
                            page_token = page.get('access_token')
                            if page_token:
                                # Update stored token if it's a page token
                                social_account.access_token = page_token
                                social_account.save()
                                return page_token, None
                            
                # If we get here, token might be invalid or page not found
                # We'll try to refresh using the user token
            except requests.RequestException:
                pass
        
        # If we don't have a valid token, try to get one using the user token
        user_token = social_account.get_token()
        if not user_token:
            return None, "No access token available. Please reconnect the account."
        
        # Get pages with access tokens
        url = "https://graph.facebook.com/v21.0/me/accounts"
        params = {
            'access_token': user_token,
            'fields': 'id,name,access_token'
        }
        
        try:
            response = requests.get(url, params=params, timeout=15)
            
            if response.status_code != 200:
                error_data = response.json() if response.text else {}
                error_msg = error_data.get('error', {}).get('message', response.text)
                return None, f"Could not fetch pages: {error_msg}"
            
            pages = response.json().get('data', [])
            
            for page in pages:
                if str(page.get('id')) == str(social_account.platform_account_id):
                    page_token = page.get('access_token')
                    if page_token:
                        # Store the page token for future use
                        social_account.access_token = page_token
                        social_account.save()
                        return page_token, None
            
            return None, f"Page ID {social_account.platform_account_id} not found in user's pages"
            
        except requests.RequestException as e:
            return None, f"Network error: {str(e)}"
    
    def publish_post(self, post, platform_status):
        """Publish post to Facebook page"""
        social_account = platform_status.social_account
        page_token, error = self.get_page_token(social_account)
        
        if error:
            return False, error
        
        page_id = social_account.platform_account_id
        url = f"https://graph.facebook.com/v21.0/{page_id}/feed"
        
        data = {
            'access_token': page_token,
            'message': post.text_content or ''
        }
        
        # Handle media
        if post.media:
            media_id = self.upload_media(post, page_token)
            if media_id:
                data['attached_media'] = f'{{"media_fbid":"{media_id}"}}'
        
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
        if not post.media:
            return None
        
        # Get media URL from Cloudinary
        media_url = post.media.url
        
        # Determine media type
        media_url_lower = media_url.lower()
        is_video = any(ext in media_url_lower for ext in ['.mp4', '.mov', '.avi', '.webm'])
        
        try:
            if not is_video:
                # Upload image
                url = "https://graph.facebook.com/v21.0/me/photos"
                data = {
                    'access_token': page_token,
                    'url': media_url,
                    'published': False
                }
                response = requests.post(url, data=data, timeout=30)
            else:
                # For videos, we need to download and upload
                # This is a simplified version - you might want to handle this differently
                url = "https://graph.facebook.com/v21.0/me/videos"
                data = {
                    'access_token': page_token,
                    'title': post.title or 'Social Media Post',
                    'description': post.text_content or ''
                }
                # Download video first (optional - can also use URL)
                # For now, we'll try with URL
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
        url = f"https://graph.facebook.com/v21.0/{post_id}"
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
        url = f"https://graph.facebook.com/v21.0/{post_id}"
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