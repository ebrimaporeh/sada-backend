from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from .models import User, Organization, OrganizationVerification, OrganizationChangeRequest


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display = ('email', 'full_name', 'role', 'region', 'is_verified', 'email_verified', 'is_active', 'created_at')
    list_filter = ('role', 'region', 'is_verified', 'email_verified', 'is_active', 'is_staff')
    search_fields = ('email', 'first_name', 'last_name', 'phone')
    ordering = ('-created_at',)
    readonly_fields = ('id', 'created_at', 'updated_at', 'last_login')

    fieldsets = (
        (None, {'fields': ('id', 'email', 'password')}),
        ('Personal Info', {'fields': ('first_name', 'last_name', 'avatar', 'phone', 'bio', 'region')}),
        ('Payment Defaults', {'fields': ('default_payment_provider', 'default_payment_phone')}),
        ('Role & Status', {'fields': ('role', 'is_active', 'is_staff', 'is_superuser', 'is_verified', 'email_verified')}),
        ('Permissions', {'fields': ('groups', 'user_permissions'), 'classes': ('collapse',)}),
        ('Timestamps', {'fields': ('created_at', 'updated_at', 'last_login')}),
    )

    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('email', 'first_name', 'last_name', 'password1', 'password2', 'role', 'is_staff'),
        }),
    )


@admin.register(Organization)
class OrganizationAdmin(admin.ModelAdmin):
    list_display = ('organization_name', 'organization_type', 'created_by', 'is_verified', 'created_at')
    list_filter = ('organization_type', 'is_verified')
    search_fields = ('organization_name', 'created_by__email')
    readonly_fields = ('id', 'created_at', 'updated_at')


@admin.register(OrganizationVerification)
class OrganizationVerificationAdmin(admin.ModelAdmin):
    list_display = ('organization', 'submitted_by', 'status', 'created_at')
    list_filter = ('status',)
    search_fields = ('organization__organization_name', 'submitted_by__email')
    readonly_fields = ('id', 'created_at', 'updated_at')


@admin.register(OrganizationChangeRequest)
class OrganizationChangeRequestAdmin(admin.ModelAdmin):
    list_display = ('organization', 'submitted_by', 'field_name', 'status', 'created_at')
    list_filter = ('field_name', 'status')
    search_fields = ('organization__organization_name', 'submitted_by__email')
    readonly_fields = ('id', 'created_at', 'updated_at')
