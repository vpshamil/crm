# crm/email_service.py
"""
Email Simulation System
=======================
Right now all emails print to the console (Django's console email backend).
The functions are structured so they can be moved to Celery tasks later
with zero changes to the callers — just swap the function call for a
Celery .delay() call.

Django email backends:
  Development  → console   (prints to terminal, no real send)
  Staging      → filebased (writes to a file)
  Production   → smtp      (sends real email via Gmail/SendGrid etc.)

Set in settings.py:
  EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'
"""

import logging
from django.core.mail import send_mail
from django.conf import settings
from django.utils import timezone

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────
# Base sender — all emails go through here
# ─────────────────────────────────────────────

def _send_email(subject, message, recipient_email, recipient_name=''):
    """
    Wrapper around Django's send_mail.
    Logs every attempt. Catches errors so email failure
    never crashes the main application flow.
    """
    logger.info(f'[EMAIL] Sending "{subject}" to {recipient_email}')

    try:
        send_mail(
            subject=subject,
            message=message,
            from_email=getattr(settings, 'DEFAULT_FROM_EMAIL', 'crm@nerve.io'),
            recipient_list=[recipient_email],
            fail_silently=False,
        )
        logger.info(f'[EMAIL] ✓ Sent successfully to {recipient_email}')
        return True

    except Exception as e:
        # Log error but don't crash — email is non-critical
        logger.error(f'[EMAIL] ✗ Failed to send to {recipient_email}: {e}')
        return False


# ─────────────────────────────────────────────
# Email 1: Lead assigned to user
# ─────────────────────────────────────────────

def send_lead_assigned_email(lead, assigned_to):
    """
    Triggered by signal when a lead is assigned/reassigned.
    Notifies the sales rep they have a new lead.
    """
    if not assigned_to.email:
        logger.warning(f'[EMAIL] No email for user {assigned_to.username}, skipping.')
        return

    subject = f'[NERVE CRM] New lead assigned: {lead.full_name}'
    message = f"""
Hi {assigned_to.get_full_name() or assigned_to.username},

A new lead has been assigned to you:

  Name    : {lead.full_name}
  Email   : {lead.email}
  Company : {lead.company or 'N/A'}
  Source  : {lead.source}
  Status  : {lead.status}
  Value   : ${lead.estimated_value or 'N/A'}

Log in to NERVE CRM to view and contact this lead.

— NERVE CRM Automated System
    """.strip()

    _send_email(subject, message, assigned_to.email)


# ─────────────────────────────────────────────
# Email 2: Lead converted to customer
# ─────────────────────────────────────────────

def send_lead_converted_email(lead, customer):
    """
    Triggered by signal when a lead is converted.
    Notifies the account manager.
    """
    manager = customer.account_manager
    if not manager or not manager.email:
        logger.warning('[EMAIL] No account manager email, skipping conversion email.')
        return

    subject = f'[NERVE CRM] Lead converted: {lead.full_name} is now a customer'
    message = f"""
Hi {manager.get_full_name() or manager.username},

Great news! A lead has been converted to a customer:

  Name          : {lead.full_name}
  Email         : {lead.email}
  Company       : {customer.company or 'N/A'}
  Tier          : {customer.tier}
  Customer Since: {customer.customer_since.strftime('%d %b %Y')}

Log in to NERVE CRM to manage this customer account.

— NERVE CRM Automated System
    """.strip()

    _send_email(subject, message, manager.email)


# ─────────────────────────────────────────────
# Email 3: Stale lead reminder
# ─────────────────────────────────────────────

def send_stale_lead_reminder(lead):
    """
    Called by a scheduled task (Celery beat) daily.
    Reminds the assigned rep to follow up.
    """
    if not lead.assigned_to or not lead.assigned_to.email:
        return

    days_since = None
    if lead.last_contacted:
        delta = timezone.now() - lead.last_contacted
        days_since = delta.days

    subject = f'[NERVE CRM] Follow-up needed: {lead.full_name}'
    message = f"""
Hi {lead.assigned_to.get_full_name() or lead.assigned_to.username},

This lead hasn't been contacted recently and needs a follow-up:

  Name          : {lead.full_name}
  Email         : {lead.email}
  Status        : {lead.status}
  Last Contacted: {'Never' if not lead.last_contacted else f'{days_since} days ago'}

Log in to NERVE CRM to take action.

— NERVE CRM Automated System
    """.strip()

    _send_email(subject, message, lead.assigned_to.email)
