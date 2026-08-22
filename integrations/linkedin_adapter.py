# integrations/linkedin_adapter.py
import requests
from .base import BaseSocialAdapter


class LinkedinAdapter(BaseSocialAdapter):
    platform = 'linkedin'

    def __init__(self, social_account=None):
        super().__init__(social_account)

    def get_page_token(self, social_account):
        stored_token = social_account.access_token if hasattr(social_account, 'access_token') else None
        if stored_token:
            return stored_token, None
        return None, 'No access token available. Please reconnect the account.'

    def _base_headers(self, token):
        return {
            'Authorization': f'Bearer {token}',
            'Content-Type': 'application/json',
            'X-Restli-Protocol-Version': '2.0.0',
        }

    def _upload_image(self, token, author_urn, image_url):
        headers = self._base_headers(token)
        register_payload = {
            "registerUploadRequest": {
                "owner": author_urn,
                "recipes": ["urn:li:digitalmediaRecipe:feedshare-image"],
                "serviceRelationships": [
                    {"identifier": "urn:li:userGeneratedContent", "relationshipType": "OWNER"}
                ],
            }
        }
        reg_res = requests.post(
            'https://api.linkedin.com/v2/assets?action=registerUpload',
            headers=headers, json=register_payload, timeout=15,
        )
        if reg_res.status_code != 200:
            return None, f"Image register failed: {reg_res.text[:200]}"

        reg_data = reg_res.json().get('value', {})
        upload_url = (
            reg_data.get('uploadMechanism', {})
            .get('com.linkedin.digitalmedia.uploading.MediaUploadHttpRequest', {})
            .get('uploadUrl')
        )
        asset_urn = reg_data.get('asset')

        if not upload_url or not asset_urn:
            return None, "Could not get upload URL"

        img_response = requests.get(image_url, timeout=30)
        if img_response.status_code != 200:
            return None, "Could not download image"

        upload_res = requests.put(
            upload_url, data=img_response.content,
            headers={'Authorization': f'Bearer {token}', 'Content-Type': 'image/jpeg'},
            timeout=60,
        )
        if upload_res.status_code not in [200, 201, 204]:
            return None, f"Image upload failed: {upload_res.status_code}"

        return asset_urn, None

    def _upload_video(self, token, author_urn, video_url):
        headers = self._base_headers(token)
        register_payload = {
            "registerUploadRequest": {
                "owner": author_urn,
                "recipes": ["urn:li:digitalmediaRecipe:feedshare-video"],
                "serviceRelationships": [
                    {"identifier": "urn:li:userGeneratedContent", "relationshipType": "OWNER"}
                ],
            }
        }
        reg_res = requests.post(
            'https://api.linkedin.com/v2/assets?action=registerUpload',
            headers=headers, json=register_payload, timeout=15,
        )
        if reg_res.status_code != 200:
            return None, f"Video register failed: {reg_res.text[:200]}"

        reg_data = reg_res.json().get('value', {})
        upload_url = (
            reg_data.get('uploadMechanism', {})
            .get('com.linkedin.digitalmedia.uploading.MediaUploadHttpRequest', {})
            .get('uploadUrl')
        )
        asset_urn = reg_data.get('asset')

        if not upload_url or not asset_urn:
            return None, "Could not get video upload URL"

        vid_response = requests.get(video_url, timeout=60)
        if vid_response.status_code != 200:
            return None, "Could not download video"

        upload_res = requests.put(
            upload_url, data=vid_response.content,
            headers={'Authorization': f'Bearer {token}', 'Content-Type': 'video/mp4'},
            timeout=120,
        )
        if upload_res.status_code not in [200, 201, 204]:
            return None, f"Video upload failed: {upload_res.status_code}"

        return asset_urn, None

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
        headers = self._base_headers(token)
        media_items = list(post.media_items.all()) if hasattr(post, 'media_items') else []

        try:
            if media_items:
                uploaded_assets = []
                media_category = 'IMAGE'

                for media in media_items:
                    if media.media_type == 'video':
                        asset_urn, upload_error = self._upload_video(token, author_urn, media.url)
                        media_category = 'VIDEO'
                    else:
                        asset_urn, upload_error = self._upload_image(token, author_urn, media.url)

                    if upload_error:
                        print(f"[LinkedIn] Upload failed: {upload_error}")
                    else:
                        uploaded_assets.append({"status": "READY", "media": asset_urn})

                if uploaded_assets:
                    ugc_payload = {
                        "author": author_urn,
                        "lifecycleState": "PUBLISHED",
                        "specificContent": {
                            "com.linkedin.ugc.ShareContent": {
                                "shareCommentary": {"text": post_content},
                                "shareMediaCategory": media_category,
                                "media": uploaded_assets,
                            }
                        },
                        "visibility": {"com.linkedin.ugc.MemberNetworkVisibility": "PUBLIC"},
                    }
                    res = requests.post('https://api.linkedin.com/v2/ugcPosts', headers=headers, json=ugc_payload, timeout=60)
                else:
                    payload = {
                        'author': author_urn,
                        'commentary': post_content,
                        'visibility': 'PUBLIC',
                        'distribution': {'feedDistribution': 'MAIN_FEED', 'targetEntities': []},
                        'lifecycleState': 'PUBLISHED',
                    }
                    res = requests.post('https://api.linkedin.com/v2/posts', headers=headers, json=payload, timeout=30)
            else:
                payload = {
                    'author': author_urn,
                    'commentary': post_content,
                    'visibility': 'PUBLIC',
                    'distribution': {'feedDistribution': 'MAIN_FEED', 'targetEntities': []},
                    'lifecycleState': 'PUBLISHED',
                }
                res = requests.post('https://api.linkedin.com/v2/posts', headers=headers, json=payload, timeout=30)

            if res.status_code in [200, 201]:
                post_id = res.headers.get('x-restli-id', '') or res.headers.get('X-RestLi-Id', '')
                if not post_id and res.text:
                    try:
                        post_id = res.json().get('id', '')
                    except Exception:
                        post_id = 'linkedin_post'
                return True, post_id or 'linkedin_post'

            error_msg = res.json().get('message', res.text) if res.text else f'HTTP {res.status_code}'
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
        if not post_id:
            return False, 'No post ID found'

    # URN encode করতে হবে — colon (:) URL এ কাজ করে না
        from urllib.parse import quote
        encoded_id = quote(post_id, safe='')

        headers = self._base_headers(token)

    # ugcPosts দিয়ে publish হলে ugcPosts এ delete, নইলে posts এ
        if 'share' in post_id or 'ugcPost' in post_id:
            url = f'https://api.linkedin.com/v2/ugcPosts/{encoded_id}'
        else:
            url = f'https://api.linkedin.com/v2/posts/{encoded_id}'

        try:
            res = requests.delete(url, headers=headers, timeout=15)
            if res.status_code == 204:
                return True, None
            error_msg = res.json().get('message', res.text) if res.text else 'LinkedIn delete failed'
            return False, error_msg
        except Exception as e:
            return False, str(e)

    def update_post(self, post, platform_status, new_text):
        return False, 'LinkedIn does not support post editing via API. Please edit manually.'