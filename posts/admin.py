from django.contrib import admin
from .models import Post

@admin.register(Post)
class PostAdmin(admin.ModelAdmin):
    list_display = ('social_account', 'status', 'scheduled_time', 'platform_post_id', 'created_at')
    fields = ('social_account', 'content', 'media_file', 'scheduled_time', 'status', 'platform_post_id', 'error_message', 'created_by')
    readonly_fields = ('platform_post_id', 'error_message')