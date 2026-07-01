from django.contrib import admin
from .models import InboxItem, Reply

admin.site.register(InboxItem)
admin.site.register(Reply)