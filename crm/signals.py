# crm/signals.py

from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver
from django.utils import timezone

from .models import Lead, Customer, ActivityLog


@receiver(pre_save, sender=Lead)
def capture_old_values(sender, instance, **kwargs):
    """Store previous status AND assigned_to before save."""
    if instance.pk:
        try:
            old = Lead.objects.get(pk=instance.pk)
            instance._old_status      = old.status
            instance._old_assigned_to = old.assigned_to
        except Lead.DoesNotExist:
            instance._old_status      = None
            instance._old_assigned_to = None
    else:
        instance._old_status      = None
        instance._old_assigned_to = None


@receiver(post_save, sender=Lead)
def log_lead_created(sender, instance, created, **kwargs):
    """Log activity when a brand new lead is created."""
    if not created:
        return
    ActivityLog.objects.create(
        lead=instance,
        performed_by=instance.assigned_to,
        activity_type=ActivityLog.ActivityType.NOTE,
        subject='Lead created',
        description=(
            f"New lead '{instance.full_name}' added "
            f"with status '{instance.status}' "
            f"from source '{instance.source}'."
        ),
        occurred_at=instance.created_at,
    )


@receiver(post_save, sender=Lead)
def log_status_change(sender, instance, created, **kwargs):
    """Log when lead status changes (except conversion)."""
    if created:
        return
    old_status = getattr(instance, '_old_status', None)
    new_status = instance.status
    if old_status == new_status or new_status == Lead.Status.CONVERTED:
        return
    ActivityLog.objects.create(
        lead=instance,
        performed_by=instance.assigned_to,
        activity_type=ActivityLog.ActivityType.STATUS_CHANGE,
        subject=f'Status changed: {old_status} → {new_status}',
        description=(
            f"Lead '{instance.full_name}' status updated "
            f"from '{old_status}' to '{new_status}'."
        ),
        occurred_at=timezone.now(),
    )


@receiver(post_save, sender=Lead)
def log_user_assigned(sender, instance, created, **kwargs):
    """Log when a lead is assigned or reassigned. Triggers email."""
    if created:
        return
    old_assigned = getattr(instance, '_old_assigned_to', None)
    new_assigned = instance.assigned_to
    if old_assigned == new_assigned:
        return

    old_name = old_assigned.username if old_assigned else 'Unassigned'
    new_name = new_assigned.username if new_assigned else 'Unassigned'

    ActivityLog.objects.create(
        lead=instance,
        performed_by=instance.assigned_to,
        activity_type=ActivityLog.ActivityType.NOTE,
        subject=f'Lead assigned: {old_name} → {new_name}',
        description=(
            f"Lead '{instance.full_name}' reassigned "
            f"from '{old_name}' to '{new_name}'."
        ),
        occurred_at=timezone.now(),
    )

    # Trigger email (imported here to avoid circular import)
    if new_assigned:
        from .email_service import send_lead_assigned_email
        send_lead_assigned_email(lead=instance, assigned_to=new_assigned)


@receiver(post_save, sender=Lead)
def handle_lead_conversion(sender, instance, created, **kwargs):
    """Lead converted → auto-create Customer + log + email."""
    if created:
        return
    old_status = getattr(instance, '_old_status', None)
    new_status = instance.status
    if old_status == Lead.Status.CONVERTED or new_status != Lead.Status.CONVERTED:
        return

    Lead.objects.filter(pk=instance.pk).update(converted_at=timezone.now())

    customer, customer_created = Customer.objects.get_or_create(
        lead=instance,
        defaults={
            'email':           instance.email,
            'phone':           instance.phone,
            'company':         instance.company or '',
            'account_manager': instance.assigned_to,
            'customer_since':  timezone.now(),
        }
    )

    ActivityLog.objects.create(
        lead=instance,
        customer=customer if customer_created else None,
        performed_by=instance.assigned_to,
        activity_type=ActivityLog.ActivityType.CONVERSION,
        subject='Lead converted to Customer',
        description=(
            f"'{instance.full_name}' converted to customer. "
            f"Customer record {'created' if customer_created else 'already existed'}."
        ),
        occurred_at=timezone.now(),
    )

    from .email_service import send_lead_converted_email
    send_lead_converted_email(lead=instance, customer=customer)
