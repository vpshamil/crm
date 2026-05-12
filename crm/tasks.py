# crm/tasks.py
"""
Background Tasks — Celery Concept
===================================
Right now these are plain Python functions.
When you add Celery, you just add @shared_task decorator
and call .delay() instead of calling directly.

WHY BACKGROUND TASKS?
  Sending email is slow (200-2000ms network call).
  If you do it inside a Django view, the user waits.
  With Celery:
    1. View finishes in <10ms
    2. Task goes into a queue (Redis/RabbitMQ)
    3. Celery worker picks it up and sends the email
    4. User never waits

CURRENT STATE (no Celery):
  send_stale_lead_reminders()  ← call manually or with cron
  send_daily_report()          ← call manually or with cron

FUTURE STATE (with Celery):
  from celery import shared_task

  @shared_task
  def send_stale_lead_reminders():
      ...

  # In Django management command or celery beat schedule:
  send_stale_lead_reminders.delay()  # runs in background
"""

import logging
from django.utils import timezone
from django.core.mail import send_mail
from django.conf import settings

logger = logging.getLogger(__name__)


def send_stale_lead_reminders(days=3):
    """
    Check all leads not contacted in N days.
    Send a reminder email to the assigned sales rep.

    Run this daily via:
      python manage.py shell -c "from crm.tasks import send_stale_lead_reminders; send_stale_lead_reminders()"

    Or schedule with Celery Beat (cron-like):
      CELERY_BEAT_SCHEDULE = {
          'daily-stale-reminders': {
              'task': 'crm.tasks.send_stale_lead_reminders',
              'schedule': crontab(hour=9, minute=0),  # 9am every day
          }
      }
    """
    from crm.models import Lead
    from crm.email_service import send_stale_lead_reminder

    stale_leads = Lead.objects.not_contacted_recently(days=days)
    count = 0

    for lead in stale_leads:
        try:
            send_stale_lead_reminder(lead)
            count += 1
        except Exception as e:
            logger.error(f'Failed to send reminder for lead {lead.id}: {e}')

    logger.info(f'[TASK] Sent {count} stale lead reminders')
    return count


def send_daily_report():
    """
    Send a daily CRM summary to all managers.
    Shows: new leads, conversions, stale leads count.

    Schedule at end of business day:
      'schedule': crontab(hour=18, minute=0)  # 6pm
    """
    from crm.models import Lead, Customer, User
    from django.db.models import Count, Q

    today = timezone.now().date()

    # All stats in as few queries as possible
    stats = Lead.objects.aggregate(
        total=Count('id'),
        new_today=Count('id', filter=Q(created_at__date=today)),
        converted_today=Count('id', filter=Q(
            status='converted',
            converted_at__date=today
        )),
    )

    stale_count = Lead.objects.not_contacted_recently(days=3).count()
    managers    = User.objects.filter(role__in=['manager', 'admin'], email__isnull=False)

    subject = f'[NERVE CRM] Daily Report — {today.strftime("%d %b %Y")}'
    message = f"""
Daily CRM Summary — {today.strftime("%d %B %Y")}

NEW LEADS TODAY    : {stats['new_today']}
CONVERSIONS TODAY  : {stats['converted_today']}
TOTAL LEADS        : {stats['total']}
STALE LEADS (3d+)  : {stale_count}

— NERVE CRM Automated System
    """.strip()

    for manager in managers:
        try:
            send_mail(
                subject=subject,
                message=message,
                from_email=getattr(settings, 'DEFAULT_FROM_EMAIL', 'crm@nerve.io'),
                recipient_list=[manager.email],
                fail_silently=True,
            )
            logger.info(f'[TASK] Daily report sent to {manager.email}')
        except Exception as e:
            logger.error(f'[TASK] Failed to send report to {manager.email}: {e}')
