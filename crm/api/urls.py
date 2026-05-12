# crm/api/urls.py

from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    LeadViewSet, CustomerViewSet, ActivityLogViewSet,
    SalesPipelineViewSet, TagViewSet, UserViewSet,
    AnalyticsView, ObtainTokenView,
)

# Router auto-generates all CRUD URLs from ViewSets
router = DefaultRouter()
router.register('leads',      LeadViewSet,          basename='lead')
router.register('customers',  CustomerViewSet,      basename='customer')
router.register('activities', ActivityLogViewSet,   basename='activity')
router.register('pipeline',   SalesPipelineViewSet, basename='pipeline')
router.register('tags',       TagViewSet,           basename='tag')
router.register('users',      UserViewSet,          basename='user')

urlpatterns = [
    path('', include(router.urls)),                  # all viewset URLs
    path('analytics/',    AnalyticsView.as_view(),   name='analytics'),
    path('auth/token/',   ObtainTokenView.as_view(), name='obtain-token'),
]
