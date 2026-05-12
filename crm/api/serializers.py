# crm/api/serializers.py

from rest_framework import serializers
from crm.models import User, Lead, Customer, SalesPipeline, ActivityLog, Tag


# ─────────────────────────────────────────────
# Tag
# ─────────────────────────────────────────────

class TagSerializer(serializers.ModelSerializer):
    class Meta:
        model = Tag
        fields = ['id', 'name', 'color']


# ─────────────────────────────────────────────
# User
# ─────────────────────────────────────────────

class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        # Never expose password — only safe fields
        fields = ['id', 'username', 'email', 'first_name', 'last_name', 'role', 'phone']
        read_only_fields = ['id']


# ─────────────────────────────────────────────
# Lead
# ─────────────────────────────────────────────

class LeadSerializer(serializers.ModelSerializer):
    """
    Full Lead serializer used for CREATE and UPDATE.
    assigned_to accepts a user ID (write).
    tags accepts a list of tag IDs (write).
    """

    # Read-only nested fields — show full objects in response
    assigned_to_detail = UserSerializer(source='assigned_to', read_only=True)
    tags_detail = TagSerializer(source='tags', many=True, read_only=True)

    # Computed field from model property
    full_name = serializers.CharField(read_only=True)

    class Meta:
        model = Lead
        fields = [
            'id',
            'first_name', 'last_name', 'full_name',
            'email', 'phone', 'company',
            'status', 'source', 'notes',
            'estimated_value',
            'assigned_to',          # write: accepts user ID
            'assigned_to_detail',   # read:  returns full user object
            'tags',                 # write: accepts list of tag IDs
            'tags_detail',          # read:  returns full tag objects
            'last_contacted',
            'converted_at',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'full_name', 'converted_at', 'created_at', 'updated_at']


class LeadListSerializer(serializers.ModelSerializer):
    """
    Lightweight serializer for list view — fewer fields, faster response.
    Used when fetching many leads at once.
    """
    full_name = serializers.CharField(read_only=True)
    assigned_to_username = serializers.CharField(
        source='assigned_to.username',
        read_only=True
    )

    class Meta:
        model = Lead
        fields = [
            'id', 'full_name', 'email', 'company',
            'status', 'source',
            'assigned_to_username',
            'last_contacted', 'created_at',
        ]


# ─────────────────────────────────────────────
# Customer
# ─────────────────────────────────────────────

class CustomerSerializer(serializers.ModelSerializer):
    """
    Customer serializer.
    lead_detail shows the originating lead's info.
    """
    lead_detail = LeadListSerializer(source='lead', read_only=True)
    account_manager_detail = UserSerializer(source='account_manager', read_only=True)

    class Meta:
        model = Customer
        fields = [
            'id',
            'lead',               # write: lead ID
            'lead_detail',        # read:  full lead object
            'account_manager',
            'account_manager_detail',
            'company', 'tier',
            'lifetime_value',
            'email', 'phone',
            'billing_address',
            'customer_since',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


# ─────────────────────────────────────────────
# ActivityLog
# ─────────────────────────────────────────────

class ActivityLogSerializer(serializers.ModelSerializer):
    performed_by_username = serializers.CharField(
        source='performed_by.username',
        read_only=True
    )

    class Meta:
        model = ActivityLog
        fields = [
            'id',
            'lead', 'customer',
            'performed_by', 'performed_by_username',
            'activity_type', 'subject', 'description',
            'outcome', 'duration_minutes',
            'occurred_at', 'created_at',
        ]
        read_only_fields = ['id', 'created_at']


# ─────────────────────────────────────────────
# SalesPipeline
# ─────────────────────────────────────────────

class SalesPipelineSerializer(serializers.ModelSerializer):
    lead_name = serializers.CharField(source='lead.full_name', read_only=True)
    owner_username = serializers.CharField(source='owner.username', read_only=True)

    class Meta:
        model = SalesPipeline
        fields = [
            'id',
            'lead', 'lead_name',
            'customer',
            'owner', 'owner_username',
            'stage', 'deal_value',
            'probability', 'expected_close_date',
            'notes',
            'stage_changed_at', 'created_at',
        ]
        read_only_fields = ['id', 'stage_changed_at', 'created_at']


# ─────────────────────────────────────────────
# Analytics (not a model — just structured data)
# ─────────────────────────────────────────────

class TopUserSerializer(serializers.Serializer):
    """Read-only serializer for top sales users query result."""
    assigned_to__id = serializers.IntegerField()
    assigned_to__username = serializers.CharField()
    converted_count = serializers.IntegerField()


class ConversionRateSerializer(serializers.Serializer):
    """Read-only serializer for conversion rate query result."""
    assigned_to__id = serializers.IntegerField()
    assigned_to__username = serializers.CharField()
    total_leads = serializers.IntegerField()
    converted_leads = serializers.IntegerField()
    conversion_rate = serializers.FloatField()
