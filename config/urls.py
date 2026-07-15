from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from drf_spectacular.views import (
    SpectacularAPIView,
    SpectacularSwaggerView,
    SpectacularRedocView,
)

urlpatterns = [
    path('admin/', admin.site.urls),

    # API v1
    path('api/v1/auth/', include('apps.authentication.urls')),
    path('api/v1/users/', include('apps.users.urls')),
    path('api/v1/campaigns/', include('apps.campaigns.urls')),
    path('api/v1/donations/', include('apps.donations.urls')),
    path('api/v1/payments/', include('apps.payments.urls')),
    path('api/v1/settings/', include('apps.common.urls')),
    path('api/v1/zakat/', include('apps.zakat.urls')),
    path('api/v1/notifications/', include('apps.notifications.urls')),
    path('api/v1/analytics/', include('apps.analytics.urls')),

    # Password reset
    path('api/v1/auth/password-reset/', include('django_rest_passwordreset.urls', namespace='password_reset')),

    # API Docs
    path('api/schema/', SpectacularAPIView.as_view(), name='schema'),
    path('api/docs/', SpectacularSwaggerView.as_view(url_name='schema'), name='swagger-ui'),
    path('api/redoc/', SpectacularRedocView.as_view(url_name='schema'), name='redoc'),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
