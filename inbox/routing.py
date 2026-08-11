from django.urls import re_path
from inbox import consumers

websocket_urlpatterns = [
    re_path(r'ws/inbox/$', consumers.InboxConsumer.as_asgi()),
]