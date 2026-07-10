import time
import requests
from .base import BaseSocialAdapter


class WhatsAppAdapter(BaseSocialAdapter):
    """
    Meta WhatsApp Cloud API adapter.
    Supports:
        - Text messages
        - Image messages (via Cloudinary URL)
        - Video messages (via Cloudinary URL)

    SocialAccount setup:
        platform              = 'whatsapp'
        platform_account_id   = WhatsApp Phone Number ID
        access_token          = Meta System User Token (permanent)
        whatsapp_business_account_id = WhatsApp Business Account ID (optional, for future use)

    Note: WhatsApp Cloud API sends to a recipient number.
    For broadcast/channel use, Meta requires approved message templates.
    Currently sending to WHATSAPP_RECIPIENT_NUMBER from settings.
    """

    API_VERSION = "v21.0"
    BASE_URL = "https://graph.facebook.com/v21.0"

    def publish_post(self, post) -> dict:
        if self._is_mock():
            time.sleep(1)
            return {'status': 'success', 'platform_post_id': f"mock_wa_{post.id}"}

        phone_number_id = self.social_account.platform_account_id
        token = self.access_token

        # Recipient: settings.WHATSAPP_RECIPIENT_NUMBER (e.g. "8801XXXXXXXXX")
        from django.conf import settings
        recipient = getattr(settings, 'WHATSAPP_RECIPIENT_NUMBER', None)
        if not recipient:
            return {
                'status': 'failed',
                'error_message': "WHATSAPP_RECIPIENT_NUMBER not set in settings/env."
            }

        try:
            if post.media_file:
                name = post.media_file.name.lower()
                public_url = self._get_public_url(post)
                if name.endswith(('.mp4', '.mov', '.avi')):
                    return self._send_video(phone_number_id, token, recipient, public_url, post.content)
                return self._send_image(phone_number_id, token, recipient, public_url, post.content)
            return self._send_text(phone_number_id, token, recipient, post.content)

        except requests.RequestException as e:
            return {'status': 'failed', 'error_message': f"WhatsApp API timeout: {e}"}

    # --- Private helpers ---

    def _get_public_url(self, post) -> str:
        url = post.media_file.url
        if url.startswith('http'):
            return url  # Cloudinary absolute URL
        from django.conf import settings
        return f"{settings.SITE_URL}{url}"

    def _send_text(self, phone_id, token, recipient, text) -> dict:
        payload = {
            "messaging_product": "whatsapp",
            "to": recipient,
            "type": "text",
            "text": {"body": text}
        }
        return self._call_api(phone_id, token, payload)

    def _send_image(self, phone_id, token, recipient, image_url, caption) -> dict:
        payload = {
            "messaging_product": "whatsapp",
            "to": recipient,
            "type": "image",
            "image": {
                "link": image_url,
                "caption": caption
            }
        }
        return self._call_api(phone_id, token, payload)

    def _send_video(self, phone_id, token, recipient, video_url, caption) -> dict:
        payload = {
            "messaging_product": "whatsapp",
            "to": recipient,
            "type": "video",
            "video": {
                "link": video_url,
                "caption": caption
            }
        }
        return self._call_api(phone_id, token, payload)

    def _call_api(self, phone_id, token, payload) -> dict:
        url = f"{self.BASE_URL}/{phone_id}/messages"
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }
        res = requests.post(url, json=payload, headers=headers, timeout=15)
        return self._handle_response(res)

    def _handle_response(self, response) -> dict:
        try:
            data = response.json()
        except Exception:
            return {'status': 'failed', 'error_message': 'Invalid JSON from WhatsApp API'}

        if response.status_code == 200 and 'messages' in data:
            message_id = data['messages'][0].get('id', '')
            return {'status': 'success', 'platform_post_id': message_id}

        error = data.get('error', {})
        error_msg = error.get('message', f"WhatsApp API error (HTTP {response.status_code})")
        return {'status': 'failed', 'error_message': error_msg}