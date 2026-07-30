import requests
from .base import BaseSocialAdapter


class FacebookAdapter(BaseSocialAdapter):
    platform = 'facebook'
    GRAPH_API = "https://graph.facebook.com/v22.0"

    def __init__(self, social_account=None):
        super().__init__(social_account)

    def get_page_token(self, social_account):
        token = getattr(social_account, 'access_token', None)
        if token:
            return token, None
        return None, "No access token found. Please reconnect the account."

    def publish_post(self, post, platform_status):
        social_account = platform_status.social_account
        page_token, error = self.get_page_token(social_account)
        if error:
            return False, error

        page_id = social_account.platform_account_id
        if not page_id:
            return False, "Page ID not found."

        post_content = getattr(post, 'content', '') or ''
        media_items = list(post.media_items.all()) if hasattr(post, 'media_items') else []

        # ── Media নেই: text-only post ──
        if not media_items:
            if not post_content:
                return False, "Post is empty."
            return self._publish_text(post_content, page_token, page_id)

        # ── Video আছে (প্রথম video নেওয়া হচ্ছে) ──
        video_items = [m for m in media_items if m.media_type == 'video']
        image_items = [m for m in media_items if m.media_type == 'image']

        if video_items:
            return self._publish_video(
                video_items[0].url, post_content, page_token, page_id
            )

        # ── শুধু image ──
        if len(image_items) == 1:
            # একটা image
            media_id = self._upload_photo(image_items[0].url, page_token, page_id)
            if not media_id:
                return False, "Failed to upload photo to Facebook."
            return self._publish_feed_with_photos([media_id], post_content, page_token, page_id)
        else:
            # একাধিক image (সর্বোচ্চ ১০টা)
            media_ids = []
            for item in image_items[:10]:
                media_id = self._upload_photo(item.url, page_token, page_id)
                if media_id:
                    media_ids.append(media_id)

            if not media_ids:
                return False, "Failed to upload photos to Facebook."
            return self._publish_feed_with_photos(media_ids, post_content, page_token, page_id)

    def _upload_photo(self, image_url, page_token, page_id):
        """Cloudinary secure_url সরাসরি Facebook-এ পাঠানো হচ্ছে"""
        url = f"{self.GRAPH_API}/{page_id}/photos"
        data = {
            'access_token': page_token,
            'url': image_url,
            'published': False,
        }
        try:
            print(f"[DEBUG] Uploading photo: {image_url}")
            response = requests.post(url, data=data, timeout=30)
            result = response.json()
            print(f"[DEBUG] Photo upload response: {result}")
            if response.status_code == 200:
                return result.get('id')
            return None
        except requests.RequestException as e:
            print(f"[DEBUG] Photo upload exception: {e}")
            return None

    def _publish_feed_with_photos(self, media_ids, post_content, page_token, page_id):
        """একটা বা একাধিক photo attach করে feed-এ post"""
        url = f"{self.GRAPH_API}/{page_id}/feed"
        attached = ','.join([f'{{"media_fbid":"{mid}"}}' for mid in media_ids])
        data = {
            'access_token': page_token,
            'message': post_content or '',
            'attached_media': f'[{attached}]',
        }
        try:
            response = requests.post(url, data=data, timeout=30)
            result = response.json()
            if response.status_code == 200:
                return True, result.get('id')
            error_msg = result.get('error', {}).get('message', response.text)
            print(f"[DEBUG] feed error: {result}")
            return False, error_msg
        except requests.RequestException as e:
            return False, str(e)

    def _publish_text(self, post_content, page_token, page_id):
        url = f"{self.GRAPH_API}/{page_id}/feed"
        data = {'access_token': page_token, 'message': post_content}
        try:
            response = requests.post(url, data=data, timeout=30)
            result = response.json()
            if response.status_code == 200:
                return True, result.get('id')
            return False, result.get('error', {}).get('message', response.text)
        except requests.RequestException as e:
            return False, str(e)

    def _publish_video(self, video_url, post_content, page_token, page_id):
        url = f"{self.GRAPH_API}/{page_id}/videos"
        data = {
            'access_token': page_token,
            'description': post_content or '',
            'file_url': video_url,
        }
        try:
            response = requests.post(url, data=data, timeout=60)
            result = response.json()
            if response.status_code == 200:
                return True, result.get('id')
            error_msg = result.get('error', {}).get('message', response.text)
            print(f"[DEBUG] video error: {result}")
            return False, error_msg
        except requests.RequestException as e:
            return False, str(e)

    def delete_post(self, post, platform_status):
        page_token, error = self.get_page_token(platform_status.social_account)
        if error:
            return False, error
        post_id = platform_status.platform_post_id
        url = f"{self.GRAPH_API}/{post_id}"
        try:
            response = requests.delete(url, params={'access_token': page_token}, timeout=15)
            if response.status_code == 200:
                return True, None
            return False, response.json().get('error', {}).get('message', response.text)
        except requests.RequestException as e:
            return False, str(e)

    def update_post(self, post, platform_status, new_text):
        page_token, error = self.get_page_token(platform_status.social_account)
        if error:
            return False, error
        post_id = platform_status.platform_post_id
        url = f"{self.GRAPH_API}/{post_id}"
        data = {'access_token': page_token, 'message': new_text}
        try:
            response = requests.post(url, data=data, timeout=15)
            if response.status_code == 200:
                return True, None
            return False, response.json().get('error', {}).get('message', response.text)
        except requests.RequestException as e:
            return False, str(e)