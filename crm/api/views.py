# crm/api/views.py
"""
Performance Optimizations Applied:
===================================
1. Custom Pagination   — control page size per endpoint
2. Query Optimization  — select_related/prefetch_related on every queryset
3. Basic Caching       — cache analytics response for 5 minutes
4. only() / defer()    — fetch only needed columns from DB
5. count() not len()   — database-level counting, not Python
"""

from django.core.cache import cache
from django.contrib.auth import authenticate

from rest_framework import viewsets, status, filters
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.authtoken.models import Token
from rest_framework.permissions import AllowAny
from rest_framework.pagination import PageNumberPagination

from crm.models import User, Lead, Customer, SalesPipeline, ActivityLog, Tag
from .serializers import (
    UserSerializer, LeadSerializer, LeadListSerializer,
    CustomerSerializer, ActivityLogSerializer, SalesPipelineSerializer,
    TagSerializer, TopUserSerializer, ConversionRateSerializer
)
from .permissions import (
    LeadPermission, AnalyticsPermission,
    IsAdmin, IsManagerOrAdmin, ReadOnlyOrAdmin, IsSalesRepOrAbove
)


# ════════════════════════════════════════════════════════
# ▌ CUSTOM PAGINATION CLASSES
#
# Why custom pagination?
# Django REST has one global PAGE_SIZE in settings.
# Different endpoints need different page sizes:
#   - Lead list     → 10 per page (table rows)
#   - Activity log  → 20 per page (timeline)
#   - Analytics     → no pagination (small dataset)
# ════════════════════════════════════════════════════════

class StandardPagination(PageNumberPagination):
    """
    Default pagination for most endpoints.
    Supports ?page_size=N override up to max 100.
    """
    page_size            = 10
    page_size_query_param = 'page_size'   # ?page_size=25
    max_page_size        = 100

    def get_paginated_response(self, data):
        """
        Override to add extra metadata to every paginated response.
        Instead of just {count, next, previous, results}
        we also return current_page and total_pages.
        """
        return Response({
            'count':        self.page.paginator.count,
            'total_pages':  self.page.paginator.num_pages,
            'current_page': self.page.number,
            'next':         self.get_next_link(),
            'previous':     self.get_previous_link(),
            'results':      data,
        })


class ActivityPagination(PageNumberPagination):
    """Larger page size for activity log — it's a timeline."""
    page_size            = 20
    page_size_query_param = 'page_size'
    max_page_size        = 100


class LargePagination(PageNumberPagination):
    """For dropdowns that need all options — tags, users."""
    page_size = 100


# ════════════════════════════════════════════════════════
# ▌ AUTH
# ════════════════════════════════════════════════════════

class ObtainTokenView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        username = request.data.get('username')
        password = request.data.get('password')
        user = authenticate(username=username, password=password)

        if not user:
            return Response(
                {'error': 'Invalid credentials'},
                status=status.HTTP_401_UNAUTHORIZED
            )

        token, created = Token.objects.get_or_create(user=user)
        return Response({
            'token':    token.key,
            'user_id':  user.id,
            'username': user.username,
            'role':     user.role,
        })


# ════════════════════════════════════════════════════════
# ▌ LEAD VIEWSET — optimized
# ════════════════════════════════════════════════════════

class LeadViewSet(viewsets.ModelViewSet):
    permission_classes  = [LeadPermission]
    pagination_class    = StandardPagination
    filter_backends     = [filters.SearchFilter, filters.OrderingFilter]
    search_fields       = ['first_name', 'last_name', 'email', 'company']
    ordering_fields     = ['created_at', 'last_contacted', 'estimated_value', 'status']
    ordering            = ['-created_at']

    def get_queryset(self):
        user = self.request.user
        role = user.role

        # ── Optimization 1: filter at DB level, not Python ──
        if role == 'sales_rep':
            qs = Lead.objects.filter(assigned_to=user)
        else:
            qs = Lead.objects.all()

        # ── Optimization 2: select_related avoids N+1 on FK ──
        # ── Optimization 3: prefetch_related avoids N+1 on M2M ──
        qs = qs.select_related('assigned_to').prefetch_related('tags')

        # ── Optimization 4: only() fetches specific columns ──
        # For list view, we don't need notes, billing_address etc.
        if self.action == 'list':
            qs = qs.only(
                'id', 'first_name', 'last_name', 'email',
                'company', 'status', 'source',
                'last_contacted', 'estimated_value',
                'assigned_to',
            )

        # Query param filters
        status_filter = self.request.query_params.get('status')
        if status_filter:
            qs = qs.filter(status=status_filter)

        assigned_to = self.request.query_params.get('assigned_to')
        if assigned_to:
            qs = qs.filter(assigned_to_id=assigned_to)

        return qs

    def get_serializer_class(self):
        if self.action == 'list':
            return LeadListSerializer
        return LeadSerializer

    def perform_create(self, serializer):
        user = self.request.user
        if user.role == 'sales_rep':
            serializer.save(assigned_to=user)
        else:
            serializer.save()

    @action(detail=True, methods=['post'])
    def convert(self, request, pk=None):
        lead = self.get_object()

        if lead.status == 'converted':
            return Response(
                {'error': 'Lead is already converted'},
                status=status.HTTP_400_BAD_REQUEST
            )
        if lead.status == 'lost':
            return Response(
                {'error': 'Cannot convert a lost lead'},
                status=status.HTTP_400_BAD_REQUEST
            )

        lead.status = 'converted'
        lead.save()

        # Invalidate analytics cache since conversion changes stats
        cache.delete('analytics_data')

        return Response({
            'message': f'{lead.full_name} successfully converted to customer',
            'lead':    LeadSerializer(lead).data,
        })

    @action(detail=False, methods=['get'])
    def stale(self, request):
        days = int(request.query_params.get('days', 3))

        if request.user.role == 'sales_rep':
            leads = Lead.objects.not_contacted_recently(days=days).filter(
                assigned_to=request.user
            )
        else:
            leads = Lead.objects.not_contacted_recently(days=days)

        # Paginate stale leads too
        page = self.paginate_queryset(leads)
        if page is not None:
            serializer = LeadListSerializer(page, many=True)
            return self.get_paginated_response(serializer.data)

        serializer = LeadListSerializer(leads, many=True)
        return Response({'days': days, 'count': leads.count(), 'results': serializer.data})

    @action(detail=True, methods=['post'])
    def log_activity(self, request, pk=None):
        lead = self.get_object()
        serializer = ActivityLogSerializer(data={
            **request.data,
            'lead':         lead.pk,
            'performed_by': request.user.pk,
        })

        if serializer.is_valid():
            serializer.save()
            if request.data.get('activity_type') in ['call', 'email', 'meeting']:
                lead.mark_contacted()
            return Response(serializer.data, status=status.HTTP_201_CREATED)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


# ════════════════════════════════════════════════════════
# ▌ CUSTOMER VIEWSET — optimized
# ════════════════════════════════════════════════════════

class CustomerViewSet(viewsets.ReadOnlyModelViewSet):
    permission_classes  = [IsSalesRepOrAbove]
    serializer_class    = CustomerSerializer
    pagination_class    = StandardPagination
    filter_backends     = [filters.SearchFilter, filters.OrderingFilter]
    search_fields       = ['lead__first_name', 'lead__last_name', 'company', 'email']
    ordering_fields     = ['customer_since', 'lifetime_value']
    ordering            = ['-customer_since']

    def get_queryset(self):
        user = self.request.user
        # ── Chained select_related: customer → lead → assigned_to ──
        # All fetched in ONE SQL query with two JOINs
        if user.role == 'sales_rep':
            return Customer.objects.filter(
                lead__assigned_to=user
            ).select_related('lead', 'lead__assigned_to', 'account_manager')

        return Customer.objects.select_related(
            'lead', 'lead__assigned_to', 'account_manager'
        )


# ════════════════════════════════════════════════════════
# ▌ ACTIVITY LOG VIEWSET — optimized
# ════════════════════════════════════════════════════════

class ActivityLogViewSet(viewsets.ModelViewSet):
    permission_classes  = [IsSalesRepOrAbove]
    serializer_class    = ActivityLogSerializer
    pagination_class    = ActivityPagination   # 20 per page
    filter_backends     = [filters.SearchFilter, filters.OrderingFilter]
    search_fields       = ['subject', 'description', 'activity_type']
    ordering            = ['-occurred_at']

    def get_queryset(self):
        user = self.request.user
        # select_related fetches performed_by, lead, customer in one query
        qs = ActivityLog.objects.select_related(
            'performed_by', 'lead', 'customer'
        )

        if user.role == 'sales_rep':
            qs = qs.filter(lead__assigned_to=user)

        # Optional filter by lead
        lead_id = self.request.query_params.get('lead')
        if lead_id:
            qs = qs.filter(lead_id=lead_id)

        # Optional filter by activity type
        activity_type = self.request.query_params.get('type')
        if activity_type:
            qs = qs.filter(activity_type=activity_type)

        return qs

    def perform_create(self, serializer):
        serializer.save(performed_by=self.request.user)


# ════════════════════════════════════════════════════════
# ▌ PIPELINE VIEWSET
# ════════════════════════════════════════════════════════

class SalesPipelineViewSet(viewsets.ModelViewSet):
    serializer_class = SalesPipelineSerializer
    pagination_class = StandardPagination
    filter_backends  = [filters.OrderingFilter]
    ordering         = ['-created_at']

    def get_permissions(self):
        if self.action == 'destroy':
            return [IsManagerOrAdmin()]
        return [IsSalesRepOrAbove()]

    def get_queryset(self):
        user = self.request.user
        qs   = SalesPipeline.objects.select_related('lead', 'owner', 'customer')

        if user.role == 'sales_rep':
            qs = qs.filter(owner=user)

        stage = self.request.query_params.get('stage')
        if stage:
            qs = qs.filter(stage=stage)

        return qs


# ════════════════════════════════════════════════════════
# ▌ ANALYTICS VIEW — with caching
#
# Caching explanation:
# Analytics queries are expensive — they scan all leads,
# group by user, compute percentages. But the data doesn't
# change every second. So we cache the result for 5 minutes.
#
# How Django cache works:
#   cache.get(key)        → returns cached value or None
#   cache.set(key, value, timeout_seconds)
#   cache.delete(key)     → manually invalidate
#
# Default cache backend: in-memory (LocMemCache)
# Production: use Redis → pip install django-redis
# ════════════════════════════════════════════════════════

class AnalyticsView(APIView):
    permission_classes = [AnalyticsPermission]

    CACHE_KEY     = 'analytics_data'
    CACHE_TIMEOUT = 60 * 5  # 5 minutes

    def get(self, request):
        # ── Step 1: Check cache first ──
        cached = cache.get(self.CACHE_KEY)
        if cached:
            # Return cached data immediately — no DB queries
            cached['from_cache'] = True
            return Response(cached)

        # ── Step 2: Cache miss — run the queries ──
        top_users        = Lead.objects.top_sales_users(limit=5)
        conversion_rates = Lead.objects.conversion_rate_per_user()
        stale_leads      = Lead.objects.not_contacted_recently(days=3)

        data = {
            'top_users':        TopUserSerializer(top_users, many=True).data,
            'conversion_rates': ConversionRateSerializer(conversion_rates, many=True).data,
            'stale_leads': {
                'count':   stale_leads.count(),   # ← count() not len() — DB level
                'results': LeadListSerializer(stale_leads[:10], many=True).data,
            },
            'from_cache': False,
        }

        # ── Step 3: Store in cache for 5 minutes ──
        cache.set(self.CACHE_KEY, data, self.CACHE_TIMEOUT)

        return Response(data)

    def delete(self, request):
        """
        DELETE /api/analytics/
        Manually invalidate the analytics cache.
        Useful after bulk operations.
        Only managers/admins can do this.
        """
        cache.delete(self.CACHE_KEY)
        return Response({'message': 'Analytics cache cleared'})


# ════════════════════════════════════════════════════════
# ▌ TAG VIEWSET
# ════════════════════════════════════════════════════════

class TagViewSet(viewsets.ModelViewSet):
    permission_classes = [ReadOnlyOrAdmin]
    pagination_class   = LargePagination
    queryset           = Tag.objects.all()
    serializer_class   = TagSerializer


# ════════════════════════════════════════════════════════
# ▌ USER VIEWSET
# ════════════════════════════════════════════════════════

class UserViewSet(viewsets.ReadOnlyModelViewSet):
    permission_classes = [IsManagerOrAdmin]
    pagination_class   = LargePagination
    serializer_class   = UserSerializer

    def get_queryset(self):
        # only() fetches just the columns we need
        # avoids loading password hash, avatar etc. for every request
        return User.objects.only(
            'id', 'username', 'email',
            'first_name', 'last_name',
            'role', 'phone'
        )
