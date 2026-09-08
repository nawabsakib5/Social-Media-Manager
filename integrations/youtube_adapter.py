# integrations/youtube_adapter.py
import requests
import os
from .base import BaseSocialAdapter


class YouTubeAdapter(BaseSocialAdapter):
    platform = 'youtube'
    BASE_URL = 'https://www.googleapis.com/youtube/v3'

    def __init__(self, social_account=None):
        super().__init__(social_account)

    def get_page_token(self, social_account):
        token = social_account.access_token
        if not token:
            return None, 'No access token. Please reconnect YouTube.'

        # Token refresh করো যদি expired হয়
        refresh_token = social_account.refresh_token
        if refresh_token:
            refreshed, error = self._refresh_token(social_account, refresh_token)
            if refreshed:
                return social_account.access_token, None

        return token, None

    def _refresh_token(self, social_account, refresh_token):
        """Access token refresh করো"""
        from django.conf import settings
        try:
            res = requests.post(
                'https://oauth2.googleapis.com/token',
                data={
                    'client_id': settings.YOUTUBE_CLIENT_ID,
                    'client_secret': settings.YOUTUBE_CLIENT_SECRET,
                    'refresh_token': refresh_token,
                    'grant_type': 'refresh_token',
                },
                timeout=15
            ).json()

            if 'access_token' in res:
                social_account.access_token = res['access_token']
                social_account.save(update_fields=['_access_token'])
                return True, None
            return False, res.get('error_description', 'Token refresh failed')
        except Exception as e:
            return False, str(e)

    def _headers(self, token):
        return {
            'Authorization': f'Bearer {token}',
            'Content-Type': 'application/json',
        }

    def publish_post(self, post, platform_status):
        """YouTube এ video upload করো"""
        social_account = platform_status.social_account
        token, error = self.get_page_token(social_account)
        if error:
            return False, error

        media_items = list(post.media_items.all()) if hasattr(post, 'media_items') else []
        video_item = next((m for m in media_items if m.media_type == 'video'), None)

        if not video_item:
            return False, 'YouTube requires a video file. No video found in this post.'

        try:
            # Video download করো
            video_res = requests.get(video_item.url, timeout=60)
            if video_res.status_code != 200:
                return False, 'Could not download video file.'

            title = (post.content or 'Untitled Video')[:100]
            description = post.content or ''

            # YouTube upload metadata
            metadata = {
                'snippet': {
                    'title': title,
                    'description': description,
                    'categoryId': '22',  # People & Blogs
                },
                'status': {
                    'privacyStatus': 'public',
                },
            }

            # Resumable upload
            init_res = requests.post(
                'https://www.googleapis.com/upload/youtube/v3/videos?uploadType=resumable&part=snippet,status',
                headers={
                    'Authorization': f'Bearer {token}',
                    'Content-Type': 'application/json',
                    'X-Upload-Content-Type': 'video/mp4',
                    'X-Upload-Content-Length': str(len(video_res.content)),
                },
                json=metadata,
                timeout=30
            )

            if init_res.status_code != 200:
                return False, f'Upload init failed: {init_res.text[:200]}'

            upload_url = init_res.headers.get('Location')
            if not upload_url:
                return False, 'No upload URL received.'

            # Video upload করো
            upload_res = requests.put(
                upload_url,
                data=video_res.content,
                headers={
                    'Content-Type': 'video/mp4',
                    'Content-Length': str(len(video_res.content)),
                },
                timeout=300
            ).json()

            video_id = upload_res.get('id')
            if video_id:
                return True, video_id
            return False, f'Upload failed: {upload_res}'

        except requests.RequestException as e:
            return False, f'Network error: {str(e)}'
        except Exception as e:
            return False, str(e)

    def delete_post(self, post, platform_status):
        """YouTube থেকে video delete করো"""
        social_account = platform_status.social_account
        token, error = self.get_page_token(social_account)
        if error:
            return False, error

        video_id = platform_status.platform_post_id
        if not video_id:
            return False, 'No video ID found.'

        try:
            res = requests.delete(
                f'{self.BASE_URL}/videos',
                headers=self._headers(token),
                params={'id': video_id},
                timeout=15
            )
            if res.status_code == 204:
                return True, None
            return False, f'Delete failed: HTTP {res.status_code}'
        except Exception as e:
            return False, str(e)

    def update_post(self, post, platform_status, new_text):
        """YouTube video title/description update করো"""
        social_account = platform_status.social_account
        token, error = self.get_page_token(social_account)
        if error:
            return False, error

        video_id = platform_status.platform_post_id
        if not video_id:
            return False, 'No video ID found.'

        try:
            # আগে video info আনো
            info_res = requests.get(
                f'{self.BASE_URL}/videos',
                headers=self._headers(token),
                params={'part': 'snippet', 'id': video_id},
                timeout=15
            ).json()

            items = info_res.get('items', [])
            if not items:
                return False, 'Video not found.'

            snippet = items[0]['snippet']
            snippet['description'] = new_text
            snippet['title'] = (new_text[:100] if new_text else snippet['title'])

            update_res = requests.put(
                f'{self.BASE_URL}/videos?part=snippet',
                headers=self._headers(token),
                json={'id': video_id, 'snippet': snippet},
                timeout=15
            ).json()

            if 'id' in update_res:
                return True, 'Updated on YouTube ✓'
            return False, update_res.get('error', {}).get('message', 'Update failed')

        except Exception as e:
            return False, str(e)

    def get_analytics(self, platform_status):
        """YouTube video analytics আনো"""
        social_account = platform_status.social_account
        token, error = self.get_page_token(social_account)
        if error:
            return {'error': error}

        video_id = platform_status.platform_post_id
        if not video_id:
            return {'error': 'No video ID'}

        try:
            res = requests.get(
                f'{self.BASE_URL}/videos',
                headers=self._headers(token),
                params={
                    'part': 'statistics',
                    'id': video_id,
                },
                timeout=15
            ).json()

            items = res.get('items', [])
            if not items:
                return {'error': 'Video not found'}

            stats = items[0].get('statistics', {})
            return {
                'likes': int(stats.get('likeCount', 0)),
                'comments': int(stats.get('commentCount', 0)),
                'views': int(stats.get('viewCount', 0)),
                'shares': 0,
                'reach': int(stats.get('viewCount', 0)),
                'impressions': int(stats.get('viewCount', 0)),
                'error': None,
            }
        except Exception as e:
            return {'error': str(e)}

    def sync_videos(self, social_account):
        """Channel এর সব videos sync করো"""
        token, error = self.get_page_token(social_account)
        if error:
            return 0, error

        channel_id = social_account.platform_account_id
        synced = 0

        try:
            # Channel এর uploads playlist ID আনো
            channel_res = requests.get(
                f'{self.BASE_URL}/channels',
                headers=self._headers(token),
                params={
                    'part': 'contentDetails',
                    'id': channel_id,
                },
                timeout=15
            ).json()

            items = channel_res.get('items', [])
            if not items:
                return 0, 'Channel not found'

            uploads_playlist = items[0]['contentDetails']['relatedPlaylists']['uploads']

            # Playlist থেকে videos আনো
            playlist_res = requests.get(
                f'{self.BASE_URL}/playlistItems',
                headers=self._headers(token),
                params={
                    'part': 'snippet',
                    'playlistId': uploads_playlist,
                    'maxResults': 50,
                },
                timeout=15
            ).json()

            video_ids = [
                item['snippet']['resourceId']['videoId']
                for item in playlist_res.get('items', [])
            ]

            if not video_ids:
                return 0, None

            # Video details আনো
            videos_res = requests.get(
                f'{self.BASE_URL}/videos',
                headers=self._headers(token),
                params={
                    'part': 'snippet,statistics',
                    'id': ','.join(video_ids),
                },
                timeout=15
            ).json()

            from posts.models import ExternalPost
            from django.utils.dateparse import parse_datetime

            for video in videos_res.get('items', []):
                snippet = video.get('snippet', {})
                stats = video.get('statistics', {})
                thumbnails = snippet.get('thumbnails', {})
                thumb_url = (
                    thumbnails.get('maxres', {}).get('url') or
                    thumbnails.get('high', {}).get('url') or
                    thumbnails.get('default', {}).get('url', '')
                )

                ExternalPost.objects.update_or_create(
                    social_account=social_account,
                    external_post_id=video['id'],
                    defaults={
                        'platform': 'youtube',
                        'content': snippet.get('description', ''),
                        'media_url': thumb_url,
                        'media_type': 'VIDEO',
                        'permalink_url': f"https://www.youtube.com/watch?v={video['id']}",
                        'likes': int(stats.get('likeCount', 0)),
                        'comments': int(stats.get('commentCount', 0)),
                        'shares': 0,
                        'reach': int(stats.get('viewCount', 0)),
                        'impressions': int(stats.get('viewCount', 0)),
                        'posted_at': parse_datetime(snippet.get('publishedAt', '')),
                    }
                )
                synced += 1

            return synced, None

        except Exception as e:
            return 0, str(e)

    def get_comments(self, social_account, video_id):
        """Video comments আনো"""
        token, error = self.get_page_token(social_account)
        if error:
            return [], error

        try:
            res = requests.get(
                f'{self.BASE_URL}/commentThreads',
                headers=self._headers(token),
                params={
                    'part': 'snippet',
                    'videoId': video_id,
                    'maxResults': 50,
                    'order': 'time',
                },
                timeout=15
            ).json()

            comments = []
            for item in res.get('items', []):
                top = item['snippet']['topLevelComment']['snippet']
                comments.append({
                    'id': item['id'],
                    'author': top.get('authorDisplayName', 'YouTube User'),
                    'text': top.get('textDisplay', ''),
                    'likes': top.get('likeCount', 0),
                    'published_at': top.get('publishedAt', ''),
                })
            return comments, None

        except Exception as e:
            return [], str(e)

    def reply_to_comment(self, social_account, parent_id, reply_text):
        """Comment এ reply করো"""
        token, error = self.get_page_token(social_account)
        if error:
            return False, error

        try:
            res = requests.post(
                f'{self.BASE_URL}/comments?part=snippet',
                headers=self._headers(token),
                json={
                    'snippet': {
                        'parentId': parent_id,
                        'textOriginal': reply_text,
                    }
                },
                timeout=15
            ).json()

            if 'id' in res:
                return True, res['id']
            return False, res.get('error', {}).get('message', 'Reply failed')

        except Exception as e:
            return False, str(e)