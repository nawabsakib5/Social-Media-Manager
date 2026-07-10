from django.contrib import admin
from .models import Post, PostPlatformStatus


class PostPlatformStatusInline(admin.TabularInline):
    model = PostPlatformStatus
    extra = 0
    readonly_fields = ('social_account', 'status', 'platform_post_id', 'error_message', 'published_at')
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(Post)
class PostAdmin(admin.ModelAdmin):
    list_display = ('content_preview', 'status', 'scheduled_time', 'created_at', 'created_by')
    list_filter = ('status',)
    search_fields = ('content',)
    readonly_fields = ('created_at', 'created_by')
    inlines = [PostPlatformStatusInline]

    def content_preview(self, obj):
        return obj.content[:40]
    content_preview.short_description = 'Content'

    def save_model(self, request, obj, form, change):
        if not obj.pk:
            obj.created_by = request.user
        super().save_model(request, obj, form, change)


@admin.register(PostPlatformStatus)
class PostPlatformStatusAdmin(admin.ModelAdmin):
    list_display = ('post', 'social_account', 'status', 'platform_post_id', 'published_at')
    list_filter = ('status', 'social_account')
    readonly_fields = ('platform_post_id', 'error_message', 'published_at')
    search_fields = ('post__content',)