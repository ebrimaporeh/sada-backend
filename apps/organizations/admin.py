from django.contrib import admin
from .models import OrganizationType, OrganizationRole, OrganizationMembership, OrganizationInvitation


@admin.register(OrganizationType)
class OrganizationTypeAdmin(admin.ModelAdmin):
    list_display = ('name', 'slug', 'is_visible')
    list_filter = ('is_visible',)
    search_fields = ('name', 'slug')
    prepopulated_fields = {'slug': ('name',)}


@admin.register(OrganizationRole)
class OrganizationRoleAdmin(admin.ModelAdmin):
    list_display = ('name', 'organization', 'created_at')
    search_fields = ('name', 'organization__organization_name')
    readonly_fields = ('id', 'created_at', 'updated_at')


@admin.register(OrganizationMembership)
class OrganizationMembershipAdmin(admin.ModelAdmin):
    list_display = ('user', 'organization', 'role', 'is_contact_person', 'created_at')
    list_filter = ('is_contact_person',)
    search_fields = ('user__email', 'organization__organization_name')
    readonly_fields = ('id', 'created_at', 'updated_at')


@admin.register(OrganizationInvitation)
class OrganizationInvitationAdmin(admin.ModelAdmin):
    list_display = ('email', 'organization', 'role', 'status', 'invited_by', 'created_at')
    list_filter = ('status',)
    search_fields = ('email', 'organization__organization_name')
    readonly_fields = ('id', 'created_at', 'updated_at')
