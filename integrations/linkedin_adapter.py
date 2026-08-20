# integrations/linkedin_adapter.py
import requests
from .base import BaseSocialAdapter


class LinkedinAdapter(BaseSocialAdapter):
    platform = 'linkedin'

    BASE_HEADERS = {
        'X-Restli-Protocol-Version': '2.0.0',
        'LinkedIn-Version': '202501',
    }

    def __init__(self, social_account=None):
        super().__init__(social_account)

    def get_page_token(self, social_account):
        stored_token = social_account.access_token if hasattr(social_account, 'access_token') else None
        if stored_token:
            return stored_token, None
        return None, 'No access token available. Please reconnect the account.'

    def _get_headers(self, token, content_type='application/json'):
        return {
            'Authorization': f'Bearer {token}',
            'Content-Type': content_type,
            **self.BASE_HEADERS,
        }

    def _upload_image(self, token, author_urn, image_url):
        headers = self._get_headers(token)

        register_payload = {
            "initializeUploadRequest": {
                "owner": author_urn
            }
        }
        reg_res = requests.post(
            'https://api.linkedin.com/rest/images?action=initializeUpload',
            headers=headers,
            json=register_payload,
            timeout=15
        )

        if reg_res.status_code not in [200, 201]:
            return None, f"Image register failed: {reg_res.text[:200]}"

        reg_data = reg_res.json().get('value', {})
        upload_url = reg_data.get('uploadUrl')
        image_urn = reg_data.get('image')

        if not upload_url or not image_urn:
            return None, "Could not get upload URL from LinkedIn"

        img_response = requests.get(image_url, timeout=30)
        if img_response.status_code != 200:
            return None, f"Could not download image"

        upload_res = requests.put(
            upload_url,
            data=img_response.content,
            headers={'Authorization': f'Bearer {token}'},
            timeout=60
        )

        if upload_res.status_code not in [200, 201, 204]:
            return None, f"Image upload failed: {upload_res.status_code}"

        return image_urn, None

    def _upload_video(self, token, author_urn, video_url):
        headers = self._get_headers(token)

        register_payload = {
            "initializeUploadRequest": {
                "owner": author_urn,
                "fileSizeBytes": 0,
                "uploadCaptions": False,
                "uploadThumbnail": False
            }
        }
        reg_res = requests.post(
            'https://api.linkedin.com/rest/videos?action=initializeUpload',
            headers=headers,
            json=register_payload,
            timeout=15
        )

        if reg_res.status_code not in [200, 201]:
            return None, f"Video register failed: {reg_res.text[:200]}"

        reg_data = reg_res.json().get('value', {})
        upload_instructions = reg_data.get('uploadInstructions', [])
        video_urn = reg_data.get('video')

        if not upload_instructions or not video_urn:
            return None, "Could not get video upload URL"

        upload_url = upload_instructions[0].get('uploadUrl')

        vid_response = requests.get(video_url, timeout=60)
        if vid_response.status_code != 200:
            return None, "Could not download video"

        upload_res = requests.put(
            upload_url,
            data=vid_response.content,
            headers={'Authorization': f'Bearer {token}'},
            timeout=120
        )

        if upload_res.status_code not in [200, 201, 204]:
            return None, f"Video upload failed: {upload_res.status_code}"

        etag = upload_res.headers.get('ETag', '')
        finalize_payload = {
            "finalizeUploadRequest": {
                "video": video_urn,
                "uploadToken": "",
                "uploadedPartIds": [etag] if etag else []
            }
        }
        requests.post(
            'https://api.linkedin.com/rest/videos?action=finalizeUpload',
            headers=headers,
            json=finalize_payload,
            timeout=15
        )

        return video_urn, None

    def publish_post(self, post, platform_status):
        social_account = platform_status.social_account
        token, error = self.get_page_token(social_account)
        if error:
            return False, error

        author_id = social_account.platform_account_id
        if not author_id:
            return False, 'LinkedIn Member ID not found. Please reconnect.'

        author_urn = f'urn:li:person:{author_id}'
        post_content = getattr(post, 'content', '') or ''
        headers = self._get_headers(token)

        media_items = list(post.media_items.all()) if hasattr(post, 'media_items') else []

        payload = {
            'author': author_urn,
            'commentary': post_content,
            'visibility': 'PUBLIC',
            'distribution': {
                'feedDistribution': 'MAIN_FEED',
                'targetEntities': [],
            },
            'lifecycleState': 'PUBLISHED',
        }

        if media_items:
            first_media = media_items[0]
            media_url = first_media.url
            media_type = first_media.media_type

            if media_type == 'video':
                asset_urn, upload_error = self._upload_video(token, author_urn, media_url)
                if upload_error:
                    print(f"[LinkedIn] Video upload failed: {upload_error}, posting text only")
                else:
                    payload['content'] = {'media': {'id': asset_urn}}
            else:
                asset_urn, upload_error = self._upload_image(token, author_urn, media_url)
                if upload_error:
                    print(f"[LinkedIn] Image upload failed: {upload_error}, posting text only")
                else:
                    payload['content'] = {'media': {'id': asset_urn}}

        try:
            res = requests.post(
                'https://api.linkedin.com/v2/posts',
                headers=headers,
                json=payload,
                timeout=30
            )

            if res.status_code in [200, 201]:
                post_id = (
                    res.headers.get('x-restli-id', '')
                    or res.headers.get('X-RestLi-Id', '')
                )
                if not post_id and res.text:
                    try:
                        post_id = res.json().get('id', '')
                    except Exception:
                        post_id = 'linkedin_post'
                return True, post_id or 'linkedin_post'

            error_msg = ''
            if res.text:
                try:
                    error_msg = res.json().get('message', res.text)
                except Exception:
                    error_msg = res.text
            else:
                error_msg = f'HTTP {res.status_code}'

            return False, f'LinkedIn API error: {error_msg}'

        except requests.RequestException as e:
            return False, f'Network error: {str(e)}'
        except Exception as e:
            return False, str(e)

    def delete_post(self, post, platform_status):
        social_account = platform_status.social_account
        token, error = self.get_page_token(social_account)
        if error:
            return False, error

        post_id = platform_status.platform_post_id
        headers = self._get_headers(token)

        try:
            res = requests.delete(
                f'https://api.linkedin.com/v2/posts/{post_id}',
                headers=headers,
                timeout=15
            )
            if res.status_code == 204:
                return True, None

            error_msg = 'LinkedIn delete failed'
            if res.text:
                try:
                    error_msg = res.json().get('message', res.text)
                except Exception:
                    error_msg = res.text
            return False, error_msg
        except requests.RequestException as e:
            return False, f'Network error: {str(e)}'
        except Exception as e:
            return False, str(e)

    def update_post(self, post, platform_status, new_text):
        return False, 'LinkedIn does not support post editing via API. Please edit manually.'