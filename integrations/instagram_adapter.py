import time
import requests
from .base import BaseSocialAdapter

class InstagramAdapter(BaseSocialAdapter):
    def publish_post(self, post) -> dict:
        if self.access_token.startswith("mock_"):
            time.sleep(2)
            return {
                'status': 'success',
                'platform_post_id': f"mock_ig_media_{post.id}"
            }
        
        # Instagram Business API requires an image or video file
        if not post.media_file:
            return {
                'status': 'failed',
                'error_message': "Instagram requires an image or video file to publish."
            }
        
        # In production, media_file.url must be a publicly accessible URL (e.g., AWS S3 or Cloudinary)
        media_url = post.media_file.url 
        
        # Step 1: Create a media container
        container_url = f"https://graph.facebook.com/v20.0/{self.social_account.platform_account_id}/media"
        container_payload = {
            'image_url': media_url,
            'caption': post.content,
            'access_token': self.access_token
        }
        
        try:
            response = requests.post(container_url, data=container_payload, timeout=15)
            container_data = response.json()
            
            if response.status_code != 200 or 'id' not in container_data:
                error_msg = container_data.get('error', {}).get('message', 'Failed to create Instagram media container.')
                return {
                    'status': 'failed',
                    'error_message': error_msg
                }
            
            creation_id = container_data['id']
            
            # Step 2: Publish the media container using the creation_id
            publish_url = f"https://graph.facebook.com/v20.0/{self.social_account.platform_account_id}/media_publish"
            publish_payload = {
                'creation_id': creation_id,
                'access_token': self.access_token
            }
            
            publish_response = requests.post(publish_url, data=publish_payload, timeout=15)
            publish_data = publish_response.json()
            
            if publish_response.status_code == 200 and 'id' in publish_data:
                return {
                    'status': 'success',
                    'platform_post_id': publish_data['id']
                }
            else:
                error_msg = publish_data.get('error', {}).get('message', 'Failed to publish Instagram media container.')
                return {
                    'status': 'failed',
                    'error_message': error_msg
                }
                
        except requests.RequestException as e:
            return {
                'status': 'failed',
                'error_message': f"Instagram API network timeout: {str(e)}"
            }