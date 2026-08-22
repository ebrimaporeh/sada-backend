from django.urls import path
from . import views

urlpatterns = [
    path('track/', views.TrackEventView.as_view(), name='event-track'),
]
