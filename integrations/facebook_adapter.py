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

    def _fix_cloudinary_url(self, url, media_type='image'):
        """
        Cloudinary /auto/upload/ URL fix করা হচ্ছে।
        Facebook শুধু /image/upload/ বা /video/upload/ accept করে।
        """
        if '/auto/upload/' in url:
            if media_type == 'video':
                url = url.replace('/auto/upload/', '/video/upload/')
            else:
                url = url.replace('/auto/upload/', '/image/upload/')
        return url

    def _detect_media_type(self, post, media_url):
        """
        Media type detect করা হচ্ছে।
        model field > URL keyword > default image
        """
        # ১. Model-এ media_type field থাকলে সেটাই সবচেয়ে reliable
        model_type = getattr(post, 'media_type', None)
        if model_type == 'video':
            return 'video'
        if model_type == 'image':
            return 'image'

        # ২. URL বা filename দেখে detect
        video_signals = [
            '.mp4', '.mov', '.avi', '.mkv', '.webm', '.flv',
            'whatsapp_video', '_video_', '/video/'
        ]
        if any(sig in media_url.lower() for sig in video_signals):
            return 'video'

        return 'image'

    def publish_post(self, post, platform_status):
        """
        Facebook Page-এ post publish।
        ৩ ধরন: text-only, image, video
        """
        social_account = platform_status.social_account
        page_token, error = self.get_page_token(social_account)
        if error:
            return False, error

        page_id = social_account.platform_account_id
        if not page_id:
            return False, "Page ID not found. Please reconnect the account."

        post_content = (
            getattr(post, 'content', '') or
            getattr(post, 'text_content', '') or ''
        )
        media_file = (
            getattr(post, 'media_file', None) or
            getattr(post, 'media', None)
        )

        # ── Media আছে কিনা চেক ──
        if media_file:
            raw_url = media_file.url
            media_type = self._detect_media_type(post, raw_url)
            print(f"[DEBUG] Media detected as: {media_type} | URL: {raw_url}")

            if media_type == 'video':
                # ভিডিও fix করে publish
                clean_url = self._fix_cloudinary_url(raw_url, 'video')
                print(f"[DEBUG] Video clean URL: {clean_url}")
                return self._publish_video(
                    clean_url, post_content, page_token, page_id
                )
            else:
                # ছবি fix করে upload, তারপর feed-এ attach
                clean_url = self._fix_cloudinary_url(raw_url, 'image')
                print(f"[DEBUG] Image clean URL: {clean_url}")
                media_id = self._upload_photo(clean_url, page_token, page_id)
                if not media_id:
                    return False, "Failed to upload photo to Facebook."
                return self._publish_feed_with_photo(
                    media_id, post_content, page_token, page_id
                )

        # ── Text only ──
        if not post_content:
            return False, "Post is empty. Please add text or media."

        return self._publish_text(post_content, page_token, page_id)

    def _upload_photo(self, image_url, page_token, page_id):
        """
        ছবি /{page_id}/photos-এ upload (published=False)।
        /me/photos নয়, page-specific endpoint।
        """
        url = f"{self.GRAPH_API}/{page_id}/photos"
        data = {
            'access_token': page_token,
            'url': image_url,
            'published': False,
        }
        try:
            response = requests.post(url, data=data, timeout=30)
            if response.status_code == 200:
                photo_id = response.json().get('id')
                print(f"[DEBUG] Photo uploaded. ID: {photo_id}")
                return photo_id
            print(f"[DEBUG] _upload_photo error: {response.json()}")
            return None
        except requests.RequestException as e:
            print(f"[DEBUG] _upload_photo exception: {e}")
            return None

    def _publish_feed_with_photo(self, media_id, post_content, page_token, page_id):
        """ছবি attach করে feed-এ post।"""
        url = f"{self.GRAPH_API}/{page_id}/feed"
        data = {
            'access_token': page_token,
            'message': post_content or '',
            'attached_media': f'[{{"media_fbid":"{media_id}"}}]',
        }
        try:
            response = requests.post(url, data=data, timeout=30)
            if response.status_code == 200:
                return True, response.json().get('id')
            error_msg = response.json().get('error', {}).get('message', response.text)
            print(f"[DEBUG] feed+photo error: {response.json()}")
            return False, error_msg
        except requests.RequestException as e:
            return False, str(e)

    def _publish_text(self, post_content, page_token, page_id):
        """Text-only feed post।"""
        url = f"{self.GRAPH_API}/{page_id}/feed"
        data = {
            'access_token': page_token,
            'message': post_content,
        }
        try:
            response = requests.post(url, data=data, timeout=30)
            if response.status_code == 200:
                return True, response.json().get('id')
            error_msg = response.json().get('error', {}).get('message', response.text)
            print(f"[DEBUG] text post error: {response.json()}")
            return False, error_msg
        except requests.RequestException as e:
            return False, str(e)

    def _publish_video(self, video_url, post_content, page_token, page_id):
        """
        ভিডিও /{page_id}/videos-এ publish।
        /me/videos নয়, page-specific endpoint।
        """
        url = f"{self.GRAPH_API}/{page_id}/videos"
        data = {
            'access_token': page_token,
            'description': post_content or '',
            'file_url': video_url,
        }
        try:
            response = requests.post(url, data=data, timeout=60)
            if response.status_code == 200:
                video_id = response.json().get('id')
                print(f"[DEBUG] Video published. ID: {video_id}")
                return True, video_id
            error_msg = response.json().get('error', {}).get('message', response.text)
            print(f"[DEBUG] _publish_video error: {response.json()}")
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
            response = requests.delete(
                url, params={'access_token': page_token}, timeout=15
            )
            if response.status_code == 200:
                return True, None
            error_msg = response.json().get('error', {}).get('message', response.text)
            return False, error_msg
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
            error_msg = response.json().get('error', {}).get('message', response.text)
            return False, error_msg
        except requests.RequestException as e:
            return False, str(e)

    # Legacy compatibility
    def upload_media(self, post, page_token, page_id=None):
        media_file = getattr(post, 'media_file', None) or getattr(post, 'media', None)
        if not media_file:
            return None
        clean_url = self._fix_cloudinary_url(media_file.url, 'image')
        return self._upload_photo(clean_url, page_token, page_id)