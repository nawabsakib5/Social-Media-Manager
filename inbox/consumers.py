import json
import asyncio
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from asgiref.sync import sync_to_async


class InboxConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.user = self.scope['user']
        if not self.user.is_authenticated:
            await self.close()
            return

        self.room_group_name = f'inbox_{self.user.id}'

        await self.channel_layer.group_add(
            self.room_group_name,
            self.channel_name
        )
        await self.accept()
        asyncio.ensure_future(self.auto_sync_loop())

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(
            self.room_group_name,
            self.channel_name
        )

    async def receive(self, text_data):
        data = json.loads(text_data)
        if data.get('action') == 'sync':
            await self.do_sync()

    async def auto_sync_loop(self):
        while True:
            try:
                await self.do_sync()
                await asyncio.sleep(5)
            except Exception:
                break

    async def do_sync(self):
        from social_accounts.models import SocialAccount
        from inbox.models import InboxItem
        from integrations.facebook_adapter import FacebookAdapter
        from inbox.views import (
            _sync_facebook_comments, _sync_facebook_messages,
            _sync_instagram_comments, _sync_instagram_messages
        )

        try:
            if self.user.is_superuser or getattr(self.user, 'user_type', None) == 'admin':
                accounts = await database_sync_to_async(
                    lambda: list(SocialAccount.objects.filter(status='connected'))
                )()
            else:
                accounts = await database_sync_to_async(
                    lambda: list(SocialAccount.objects.filter(
                        permitted_users=self.user, status='connected'
                    ))
                )()

            adapter = FacebookAdapter()
            synced = 0

            for account in accounts:
                page_token, error = await database_sync_to_async(
                    adapter.get_page_token
                )(account)
                if error:
                    continue

                try:
                    if account.platform == 'facebook':
                        synced += await database_sync_to_async(_sync_facebook_comments)(account, page_token)
                        synced += await database_sync_to_async(_sync_facebook_messages)(account, page_token)
                    elif account.platform == 'instagram':
                        synced += await database_sync_to_async(_sync_instagram_comments)(account, page_token)
                        synced += await database_sync_to_async(_sync_instagram_messages)(account, page_token)
                except Exception as e:
                    print(f"[WS Sync Error] {account.account_name}: {e}")

            if self.user.is_superuser or getattr(self.user, 'user_type', None) == 'admin':
                unread = await database_sync_to_async(
                    lambda: InboxItem.objects.filter(is_read=False).count()
                )()
            else:
                unread = await database_sync_to_async(
                    lambda: InboxItem.objects.filter(
                        social_account__permitted_users=self.user,
                        is_read=False
                    ).count()
                )()

            await self.send(text_data=json.dumps({
                'type': 'sync_update',
                'synced': synced,
                'unread_count': unread,
                'reload': synced > 0,
            }))

        except Exception as e:
            print(f"[WS Consumer Error]: {e}")

    async def inbox_message(self, event):
        await self.send(text_data=json.dumps(event['message']))