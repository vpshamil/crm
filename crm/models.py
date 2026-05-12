# crm/models.py

from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils import timezone
from django.db.models import Count, Q
from django.db.models import FloatField, ExpressionWrapper, F
from django.db.models.functions import Cast


# ─────────────────────────────────────────────
# Custom Manager for Lead
# ─────────────────────────────────────────────

class LeadManager(models.Manager):
    """Custom manager with business-logic querysets."""

    def not_contacted_recently(self, days=3):
        """Leads not contacted in the last N days."""
        cutoff = timezone.now() - timezone.timedelta(days=days)
        return self.filter(
            Q(last_contacted__lt=cutoff) | Q(last_contacted__isnull=True),
            status__in=['new', 'contacted', 'qualified']
        )

    def active(self):
        """All leads that are not lost or converted."""
        return self.exclude(status__in=['lost', 'converted'])

    def conversion_rate_per_user(self):
        """
        Returns queryset annotated with:
          - total_leads
          - converted_leads
          - conversion_rate (as float 0-100)
        Grouped by assigned_to user.
        """

        return (
            self.values('assigned_to__id', 'assigned_to__username')
            .annotate(
                total_leads=Count('id'),
                converted_leads=Count('id', filter=Q(status='converted')),
            )
            .annotate(
                conversion_rate=ExpressionWrapper(
                    Cast('converted_leads', FloatField()) * 100.0
                    / Cast('total_leads', FloatField()),
                    output_field=FloatField()
                )
            )
            .order_by('-conversion_rate')
        )

    def top_sales_users(self, limit=5):
        """Top N users by number of converted leads."""
        return (
            self.filter(status='converted')
            .values('assigned_to__id', 'assigned_to__username')
            .annotate(converted_count=Count('id'))
            .order_by('-converted_count')[:limit]
        )


# ─────────────────────────────────────────────
# Custom User Model
# ─────────────────────────────────────────────

class User(AbstractUser):
    """
    Extended user model for CRM.
    Inherits: username, email, first_name, last_name, is_staff, etc.
    """

    class Role(models.TextChoices):
        ADMIN = 'admin', 'Admin'
        SALES_REP = 'sales_rep', 'Sales Representative'
        MANAGER = 'manager', 'Manager'

    role = models.CharField(
        max_length=20,
        choices=Role.choices,
        default=Role.SALES_REP
    )
    phone = models.CharField(max_length=20, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'crm_users'
        verbose_name = 'User'
        verbose_name_plural = 'Users'

    def __str__(self):
        return f"{self.get_full_name() or self.username} ({self.role})"


# ─────────────────────────────────────────────
# Lead
# ─────────────────────────────────────────────

class Lead(models.Model):

    class Status(models.TextChoices):
        NEW = 'new', 'New'
        CONTACTED = 'contacted', 'Contacted'
        QUALIFIED = 'qualified', 'Qualified'
        CONVERTED = 'converted', 'Converted'
        LOST = 'lost', 'Lost'

    class Source(models.TextChoices):
        WEBSITE = 'website', 'Website'
        REFERRAL = 'referral', 'Referral'
        SOCIAL = 'social', 'Social Media'
        COLD_CALL = 'cold_call', 'Cold Call'
        EMAIL = 'email', 'Email Campaign'
        OTHER = 'other', 'Other'

    # Core identity
    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100)
    email = models.EmailField(unique=True)
    phone = models.CharField(max_length=20, blank=True)
    company = models.CharField(max_length=200, blank=True)

    # CRM metadata
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.NEW,
        db_index=True
    )
    source = models.CharField(
        max_length=20,
        choices=Source.choices,
        default=Source.OTHER
    )
    notes = models.TextField(blank=True)
    estimated_value = models.DecimalField(
        max_digits=12, decimal_places=2,
        null=True, blank=True
    )

    # Relationships
    assigned_to = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='assigned_leads'
    )
    tags = models.ManyToManyField(
        'Tag',
        blank=True,
        related_name='leads'
    )

    # Timestamps
    last_contacted = models.DateTimeField(null=True, blank=True)
    converted_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # Custom manager
    objects = LeadManager()

    class Meta:
        db_table = 'crm_leads'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['status', 'assigned_to']),
            models.Index(fields=['last_contacted']),
            models.Index(fields=['created_at']),
        ]

    def __str__(self):
        return f"{self.first_name} {self.last_name} <{self.email}> [{self.status}]"

    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name}"
        

    def mark_contacted(self):
        """Update last_contacted timestamp and set status to contacted."""
        self.last_contacted = timezone.now()
        if self.status == self.Status.NEW:
            self.status = self.Status.CONTACTED
        self.save(update_fields=['last_contacted', 'status', 'updated_at'])


# ─────────────────────────────────────────────
# Customer (converted from Lead)
# ─────────────────────────────────────────────

class Customer(models.Model):
    """
    Created automatically via signal when Lead.status = 'converted'.
    """

    class Tier(models.TextChoices):
        BRONZE = 'bronze', 'Bronze'
        SILVER = 'silver', 'Silver'
        GOLD = 'gold', 'Gold'
        PLATINUM = 'platinum', 'Platinum'

    # OneToOne link back to the originating Lead
    lead = models.OneToOneField(
        Lead,
        on_delete=models.PROTECT,   # never delete customer if lead deleted
        related_name='customer'
    )

    # Relationship owner
    account_manager = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='managed_customers'
    )

    # Business data
    company = models.CharField(max_length=200)
    tier = models.CharField(
        max_length=10,
        choices=Tier.choices,
        default=Tier.BRONZE
    )
    lifetime_value = models.DecimalField(
        max_digits=14, decimal_places=2,
        default=0
    )

    # Contact details (copied/overridden from Lead)
    email = models.EmailField()
    phone = models.CharField(max_length=20, blank=True)
    billing_address = models.TextField(blank=True)

    # Timestamps
    customer_since = models.DateTimeField(default=timezone.now)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'crm_customers'
        ordering = ['-customer_since']

    def __str__(self):
        return f"{self.lead.full_name} — {self.company} ({self.tier})"


# ─────────────────────────────────────────────
# SalesPipeline
# ─────────────────────────────────────────────

class SalesPipeline(models.Model):

    class Stage(models.TextChoices):
        PROSPECTING = 'prospecting', 'Prospecting'
        QUALIFICATION = 'qualification', 'Qualification'
        PROPOSAL = 'proposal', 'Proposal'
        NEGOTIATION = 'negotiation', 'Negotiation'
        CLOSED_WON = 'closed_won', 'Closed Won'
        CLOSED_LOST = 'closed_lost', 'Closed Lost'

    # A pipeline entry is tied to a Lead (and optionally a Customer)
    lead = models.ForeignKey(
        Lead,
        on_delete=models.CASCADE,
        related_name='pipeline_entries'
    )
    customer = models.ForeignKey(
        Customer,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='pipeline_entries'
    )
    owner = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        related_name='pipeline_entries'
    )

    stage = models.CharField(
        max_length=20,
        choices=Stage.choices,
        default=Stage.PROSPECTING,
        db_index=True
    )
    deal_value = models.DecimalField(
        max_digits=14, decimal_places=2,
        null=True, blank=True
    )
    probability = models.PositiveSmallIntegerField(
        default=0,
        help_text="Win probability 0–100%"
    )
    expected_close_date = models.DateField(null=True, blank=True)
    notes = models.TextField(blank=True)

    # Timestamps
    stage_changed_at = models.DateTimeField(auto_now=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'crm_sales_pipeline'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['stage', 'owner']),
            models.Index(fields=['expected_close_date']),
        ]

    def __str__(self):
        return f"[{self.stage}] {self.lead} — ${self.deal_value}"


# ─────────────────────────────────────────────
# ActivityLog
# ─────────────────────────────────────────────

class ActivityLog(models.Model):

    class ActivityType(models.TextChoices):
        CALL = 'call', 'Call'
        EMAIL = 'email', 'Email'
        MEETING = 'meeting', 'Meeting'
        NOTE = 'note', 'Note'
        STATUS_CHANGE = 'status_change', 'Status Change'
        CONVERSION = 'conversion', 'Conversion'

    # Polymorphic-ish: log can be tied to Lead OR Customer (or both)
    lead = models.ForeignKey(
        Lead,
        on_delete=models.CASCADE,
        null=True, blank=True,
        related_name='activities'
    )
    customer = models.ForeignKey(
        Customer,
        on_delete=models.CASCADE,
        null=True, blank=True,
        related_name='activities'
    )
    performed_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        related_name='activities'
    )

    activity_type = models.CharField(
        max_length=20,
        choices=ActivityType.choices,
        db_index=True
    )
    subject = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    outcome = models.CharField(max_length=255, blank=True)
    duration_minutes = models.PositiveIntegerField(null=True, blank=True)

    # When the activity actually happened (may differ from created_at)
    occurred_at = models.DateTimeField(default=timezone.now)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'crm_activity_log'
        ordering = ['-occurred_at']
        indexes = [
            models.Index(fields=['activity_type', 'occurred_at']),
            models.Index(fields=['lead', 'occurred_at']),
        ]

    def __str__(self):
        target = self.lead or self.customer
        return f"[{self.activity_type}] {self.subject} → {target}"


# ─────────────────────────────────────────────
# Tag (ManyToMany helper)
# ─────────────────────────────────────────────

class Tag(models.Model):
    name = models.CharField(max_length=50, unique=True)
    color = models.CharField(max_length=7, default='#6B7280')  # hex color

    class Meta:
        db_table = 'crm_tags'
        ordering = ['name']

    def __str__(self):
        return self.name
