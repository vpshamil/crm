# crm/views.py

from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.db.models import Count, Prefetch

from .models import Lead, Customer, SalesPipeline, ActivityLog,User


# ════════════════════════════════════════════════════════
# ▌ DASHBOARD
# ════════════════════════════════════════════════════════

@login_required
def dashboard(request):
    context = {
        # All query logic lives in the manager — views just call by name
        'top_users': Lead.objects.top_sales_users(limit=5),
        'stale_leads': Lead.objects.not_contacted_recently(days=3)[:5],

        # Simple counts — fine to do directly in view
        'total_leads': Lead.objects.count(),
        'total_customers': Customer.objects.count(),
        'open_deals': SalesPipeline.objects.exclude(
            stage__in=[SalesPipeline.Stage.CLOSED_WON, SalesPipeline.Stage.CLOSED_LOST]
        ).count(),

        # Recent activity — specific to dashboard, not reused elsewhere
        'recent_activities': (
            ActivityLog.objects
            .select_related('performed_by', 'lead', 'customer')
            .order_by('-occurred_at')[:10]
        ),
    }
    return render(request, 'crm/dashboard.html', context)


# ════════════════════════════════════════════════════════
# ▌ LEAD VIEWS
# ════════════════════════════════════════════════════════

@login_required
def lead_list(request):
    status_filter = request.GET.get('status', '')

    leads = (
        Lead.objects
        .select_related('assigned_to')
        .prefetch_related('tags')
        .order_by('-created_at')
    )

    if status_filter:
        leads = leads.filter(status=status_filter)

    context = {
        'leads': leads,
        'status_choices': Lead.Status.choices,
        'current_status': status_filter,
    }
    return render(request, 'crm/lead_list.html', context)
    


@login_required
def lead_detail(request, pk):
    lead = get_object_or_404(
        Lead.objects
        .select_related('assigned_to', 'customer')
        .prefetch_related(
            'tags',
            Prefetch(
                'activities',
                queryset=ActivityLog.objects
                    .select_related('performed_by')
                    .order_by('-occurred_at'),
            ),
            Prefetch(
                'pipeline_entries',
                queryset=SalesPipeline.objects
                    .select_related('owner')
                    .order_by('-created_at'),
            )
        ),
        pk=pk
    )
    return render(request, 'crm/lead_detail.html', {'lead': lead})


@login_required
def lead_update_status(request, pk):
    if request.method != 'POST':
        return redirect('lead_detail', pk=pk)

    lead = get_object_or_404(Lead, pk=pk)
    new_status = request.POST.get('status')

    if new_status in dict(Lead.Status.choices):
        lead.status = new_status
        lead.save()  # signals fire here automatically

    return redirect('lead_detail', pk=pk)


@login_required
def log_activity(request, lead_pk):
    if request.method != 'POST':
        return redirect('lead_detail', pk=lead_pk)

    lead = get_object_or_404(Lead, pk=lead_pk)

    ActivityLog.objects.create(
        lead=lead,
        performed_by=request.user,
        activity_type=request.POST.get('activity_type'),
        subject=request.POST.get('subject', ''),
        description=request.POST.get('description', ''),
        duration_minutes=request.POST.get('duration_minutes') or None,
    )

    # If it's a contact activity, update last_contacted on the lead
    if request.POST.get('activity_type') in [
        ActivityLog.ActivityType.CALL,
        ActivityLog.ActivityType.EMAIL,
        ActivityLog.ActivityType.MEETING,
    ]:
        lead.mark_contacted()  # model method handles the logic

    return redirect('lead_detail', pk=lead_pk)


# ════════════════════════════════════════════════════════
# ▌ CUSTOMER VIEWS
# ════════════════════════════════════════════════════════

@login_required
def customer_list(request):
    customers = (
        Customer.objects
        .select_related('lead', 'lead__assigned_to', 'account_manager')
        .order_by('-customer_since')
    )
    return render(request, 'crm/customer_list.html', {'customers': customers})


@login_required
def customer_detail(request, pk):
    customer = get_object_or_404(
        Customer.objects
        .select_related('lead', 'account_manager')
        .prefetch_related(
            Prefetch(
                'activities',
                queryset=ActivityLog.objects
                    .select_related('performed_by')
                    .order_by('-occurred_at'),
            ),
            Prefetch(
                'pipeline_entries',
                queryset=SalesPipeline.objects
                    .select_related('owner')
                    .order_by('-created_at'),
            )
        ),
        pk=pk
    )
    return render(request, 'crm/customer_detail.html', {'customer': customer})


# ════════════════════════════════════════════════════════
# ▌ ANALYTICS
# ════════════════════════════════════════════════════════

@login_required
def sales_analytics(request):
    context = {
        'top_users': Lead.objects.top_sales_users(limit=5),
        'stale_leads': Lead.objects.not_contacted_recently(days=3),
        'conversion_rates': Lead.objects.conversion_rate_per_user(),
    }
    return render(request, 'crm/analytics.html', context)


@login_required
def analytics_json(request):
    """JSON endpoint for feeding frontend charts."""
    return JsonResponse({
        'top_users': list(Lead.objects.top_sales_users(limit=5)),
        'conversion_rates': [
            {
                'username': r['assigned_to__username'],
                'total': r['total_leads'],
                'converted': r['converted_leads'],
                'rate': round(r['conversion_rate'], 2),
            }
            for r in Lead.objects.conversion_rate_per_user()
        ],
        'stale_lead_count': Lead.objects.not_contacted_recently(days=3).count(),
    })


# ════════════════════════════════════════════════════════
# ▌ PIPELINE
# ════════════════════════════════════════════════════════

@login_required
def pipeline_board(request):
    entries = (
        SalesPipeline.objects
        .select_related('lead', 'owner', 'customer')
        .order_by('stage', '-deal_value')
    )

    # Group by stage in Python after single fetch
    board = {
        stage_value: {
            'label': stage_label,
            'entries': [e for e in entries if e.stage == stage_value]
        }
        for stage_value, stage_label in SalesPipeline.Stage.choices
    }

    return render(request, 'crm/pipeline_board.html', {'board': board})


# ════════════════════════════════════════════════════════
# ▌ LEAD CREATE
# ════════════════════════════════════════════════════════

@login_required
def lead_create(request):
    if request.method == 'POST':
        Lead.objects.create(
            first_name=request.POST.get('first_name'),
            last_name=request.POST.get('last_name'),
            email=request.POST.get('email'),
            phone=request.POST.get('phone', ''),
            company=request.POST.get('company', ''),
            source=request.POST.get('source', 'other'),
            notes=request.POST.get('notes', ''),
            estimated_value=request.POST.get('estimated_value') or None,
            assigned_to_id=request.POST.get('assigned_to') or None,
        )
        return redirect('lead_list')

    users = User.objects.filter(role='sales_rep')
    return render(request, 'crm/lead_create.html', {'users': users})

def lead_dashboard(request):
    return render(request, 'crm/lead_dashboard.html')