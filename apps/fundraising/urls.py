from django.urls import path

from . import embed_views, poster_views

urlpatterns = [
    path('posters/', poster_views.PosterListCreateView.as_view(), name='poster-list-create'),
    path('posters/<uuid:pk>/', poster_views.PosterDetailView.as_view(), name='poster-detail'),
    path('posters/<uuid:pk>/images/', poster_views.PosterImageUploadView.as_view(), name='poster-image-upload'),

    path('organizations/<uuid:organization_id>/embed/', embed_views.OrganizationEmbedView.as_view(), name='organization-embed'),
    path('embeds/<uuid:pk>/', embed_views.EmbedDetailView.as_view(), name='embed-detail'),
    path('embeds/<uuid:pk>/activate/', embed_views.EmbedActivateView.as_view(), name='embed-activate'),
    path('embeds/<uuid:pk>/deactivate/', embed_views.EmbedDeactivateView.as_view(), name='embed-deactivate'),
    path('embeds/<uuid:pk>/public/', embed_views.EmbedPublicView.as_view(), name='embed-public'),
]
