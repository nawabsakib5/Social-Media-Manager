import time
import requests
from .base import BaseSocialAdapter


class InstagramAdapter(BaseSocialAdapter):
    BASE_URL = "https://graph.facebook.com/v22.0"

    def __init__(self, social_account=None):
        super().__init__(social_account)

    def publish_post(self, post, platform_status):
        if self._is_mock():
            return True, f"mock_ig_{post.id}"

        media_items = list(post.media_items.all()) if hasattr(post, 'media_items') else []
        if not media_items:
            return False, "Instagram requires an image or video."

        first_media = media_items[0]
        public_url = first_media.url
        is_video = first_media.media_type == 'video'

        social_account = platform_status.social_account
        ig_id = social_account.platform_account_id

        print(f"[DEBUG Instagram] ig_id: {ig_id}")
        print(f"[DEBUG Instagram] public_url: {public_url}")
        print(f"[DEBUG Instagram] is_video: {is_video}")

        if not ig_id:
            return False, "No Instagram Business account connected."

        from .facebook_adapter import FacebookAdapter
        token, error = FacebookAdapter().get_page_token(social_account)
        if error:
            return False, error

        try:
            if is_video:
                return self._publish_video(post, ig_id, token, public_url)
            else:
                return self._publish_photo(post, ig_id, token, public_url)
        except requests.RequestException as e:
            return False, f"Instagram API timeout: {e}"
        except Exception as e:
            return False, str(e)

    def _publish_photo(self, post, ig_id, token, public_url):
        try:
            container_id = self._create_container(ig_id, token, {
                'image_url': public_url,
                'caption': post.content or '',
                'access_token': token,
            })
            return self._publish_container(ig_id, token, container_id)
        except Exception as e:
            return False, str(e)

    def _publish_video(self, post, ig_id, token, public_url):
        try:
            container_id = self._create_container(ig_id, token, {
                'video_url': public_url,
                'caption': post.content or '',
                'media_type': 'REELS',
                'access_token': token,
            })

            
            status_url = f"{self.BASE_URL}/{container_id}"
            max_attempts = 20  
            for attempt in range(max_attempts):
                time.sleep(5)
                status_res = requests.get(
                    status_url,
                    params={'fields': 'status_code', 'access_token': token},
                    timeout=15
                ).json()
                status_code = status_res.get('status_code', '')
                print(f"[DEBUG IG Video Status] attempt {attempt+1}: {status_code}")

                if status_code == 'FINISHED':
                    break
                elif status_code == 'ERROR':
                    return False, "Instagram video processing failed."

            return self._publish_container(ig_id, token, container_id)
        except Exception as e:
            return False, str(e)

    def _create_container(self, ig_id, token, payload) -> str:
        url = f"{self.BASE_URL}/{ig_id}/media"
        print(f"[DEBUG IG Container] URL: {url}")
        print(f"[DEBUG IG Container] Payload: {payload}")
        res = requests.post(url, data=payload, timeout=60)
        data = res.json()
        print(f"[DEBUG IG Container] Response: {data}")
        if 'id' in data:
            return data['id']
        error = data.get('error', {}).get('message', 'Unknown error')
        raise ValueError(f"Container creation failed: {error}")

    def _publish_container(self, ig_id, token, creation_id):
        url = f"{self.BASE_URL}/{ig_id}/media_publish"
        print(f"[DEBUG IG Publish] creation_id: {creation_id}")
        res = requests.post(
            url,
            data={'creation_id': creation_id, 'access_token': token},
            timeout=30
        )
        data = res.json()
        print(f"[DEBUG IG Publish] Response: {data}")
        if 'id' in data:
            return True, data['id']
        error = data.get('error', {}).get('message', 'Publish failed')
        return False, error

    def delete_post(self, post, platform_status):
        return False, "Instagram posts cannot be deleted via API. Please delete manually."

    def update_post(self, post, platform_status, new_text):
        return False, "Instagram captions cannot be updated via API. Please edit manually."