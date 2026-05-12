from django.contrib import admin
from .models import User, Lead, Customer, SalesPipeline, ActivityLog, Tag

@admin.register(Lead)
class LeadAdmin(admin.ModelAdmin):
    list_display = ['full_name', 'email', 'status', 'assigned_to', 'last_contacted']
    list_filter = ['status', 'source']
    search_fields = ['first_name', 'last_name', 'email']

@admin.register(Customer)
class CustomerAdmin(admin.ModelAdmin):
    list_display = ['lead', 'company', 'tier', 'account_manager', 'customer_since']

@admin.register(ActivityLog)
class ActivityLogAdmin(admin.ModelAdmin):
    list_display = ['activity_type', 'subject', 'lead', 'performed_by', 'occurred_at']

admin.site.register(User)
admin.site.register(SalesPipeline)
admin.site.register(Tag)
