from django.contrib import admin
from .models import Organization, Membership


class MembershipInline(admin.TabularInline):
    model = Membership
    extra = 0


@admin.register(Organization)
class OrganizationAdmin(admin.ModelAdmin):
    list_display = ('name', 'slug', 'is_active', 'created_by', 'created_at')
    prepopulated_fields = {'slug': ('name',)}
    inlines = [MembershipInline]


@admin.register(Membership)
class MembershipAdmin(admin.ModelAdmin):
    list_display = ('user', 'organization', 'role', 'joined_at')
    list_filter = ('role', 'organization')