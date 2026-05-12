# crm/management/commands/seed_data.py

import random
from datetime import timedelta
from django.core.management.base import BaseCommand
from django.utils import timezone
from crm.models import User, Lead, Customer, ActivityLog, SalesPipeline, Tag


FIRST_NAMES = [
    'James', 'Mary', 'Robert', 'Patricia', 'John', 'Jennifer', 'Michael',
    'Linda', 'William', 'Barbara', 'David', 'Susan', 'Richard', 'Jessica',
    'Joseph', 'Sarah', 'Thomas', 'Karen', 'Charles', 'Lisa', 'Arjun',
    'Priya', 'Mohammed', 'Fatima', 'Wei', 'Mei', 'Carlos', 'Sofia'
]

LAST_NAMES = [
    'Smith', 'Johnson', 'Williams', 'Brown', 'Jones', 'Garcia', 'Miller',
    'Davis', 'Wilson', 'Taylor', 'Anderson', 'Thomas', 'Jackson', 'White',
    'Harris', 'Martin', 'Thompson', 'Young', 'Patel', 'Kumar', 'Khan',
    'Chen', 'Wang', 'Rodriguez', 'Martinez', 'Lopez', 'Nair', 'Menon'
]

COMPANIES = [
    'Acme Corp', 'Globex', 'Initech', 'Umbrella Ltd', 'Stark Industries',
    'Wayne Enterprises', 'Cyberdyne', 'Soylent Corp', 'Massive Dynamic',
    'Aperture Science', 'Weyland Corp', 'InGen Technologies', 'Rekall Inc',
    'Tyrell Corp', 'Oscorp', 'LexCorp', 'Veridian Dynamics', 'Goliath National'
]

SALES_USERNAMES = ['alice', 'bob', 'carol', 'david', 'eve']


class Command(BaseCommand):
    help = 'Seed the database with realistic CRM test data'

    def add_arguments(self, parser):
        parser.add_argument(
            '--leads', type=int, default=50,
            help='Number of leads to create (default: 50)'
        )
        parser.add_argument(
            '--clear', action='store_true',
            help='Clear existing data before seeding'
        )

    def handle(self, *args, **options):
        if options['clear']:
            self.stdout.write('Clearing existing data...')
            ActivityLog.objects.all().delete()
            SalesPipeline.objects.all().delete()
            Customer.objects.all().delete()
            Lead.objects.all().delete()
            User.objects.filter(is_superuser=False).delete()
            Tag.objects.all().delete()
            self.stdout.write(self.style.WARNING('Cleared.'))

        # ── Step 1: Create sales users ──────────────────────────
        self.stdout.write('Creating sales users...')
        users = []
        for name in SALES_USERNAMES:
            user, created = User.objects.get_or_create(
                username=name,
                defaults={
                    'email': f'{name}@crm.com',
                    'first_name': name.capitalize(),
                    'last_name': 'Sales',
                    'role': User.Role.SALES_REP,
                }
            )
            if created:
                user.set_password('test123')
                user.save()
            users.append(user)
        self.stdout.write(self.style.SUCCESS(f'  {len(users)} users ready'))

        # ── Step 2: Create tags ─────────────────────────────────
        tag_names = ['hot', 'cold', 'enterprise', 'startup', 'follow-up', 'vip']
        tags = []
        for name in tag_names:
            tag, _ = Tag.objects.get_or_create(name=name)
            tags.append(tag)
        self.stdout.write(self.style.SUCCESS(f'  {len(tags)} tags ready'))

        # ── Step 3: Create leads ────────────────────────────────
        self.stdout.write(f'Creating {options["leads"]} leads...')
        leads = []
        statuses = ['new', 'contacted', 'qualified', 'converted', 'lost']

        # Weight distribution — more realistic
        status_weights = [25, 30, 20, 15, 10]

        for i in range(options['leads']):
            first = random.choice(FIRST_NAMES)
            last = random.choice(LAST_NAMES)
            status = random.choices(statuses, weights=status_weights, k=1)[0]
            assigned = random.choice(users)

            # Randomise last_contacted — some never contacted, some recently, some stale
            contact_choice = random.choice(['never', 'recent', 'stale'])
            if contact_choice == 'never':
                last_contacted = None
            elif contact_choice == 'recent':
                last_contacted = timezone.now() - timedelta(days=random.randint(0, 2))
            else:
                last_contacted = timezone.now() - timedelta(days=random.randint(4, 30))

            lead = Lead(
                first_name=first,
                last_name=last,
                email=f'{first.lower()}.{last.lower()}{i}@example.com',
                phone=f'+91 98{random.randint(10000000, 99999999)}',
                company=random.choice(COMPANIES),
                status=status,
                source=random.choice(Lead.Source.values),
                assigned_to=assigned,
                last_contacted=last_contacted,
                estimated_value=random.choice([
                    5000, 10000, 25000, 50000, 100000, 250000
                ]),
                notes=f'Auto-generated lead #{i+1}',
                converted_at=timezone.now() if status == 'converted' else None,
            )
            leads.append(lead)

        # bulk_create skips signals intentionally — we handle related data below
        Lead.objects.bulk_create(leads)
        created_leads = list(Lead.objects.order_by('-created_at')[:options['leads']])

        # Assign random tags to each lead
        for lead in created_leads:
            lead.tags.set(random.sample(tags, k=random.randint(0, 3)))

        self.stdout.write(self.style.SUCCESS(f'  {len(created_leads)} leads created'))

        # ── Step 4: Create Customers for converted leads ────────
        self.stdout.write('Creating customers for converted leads...')
        converted_leads = Lead.objects.filter(status='converted')
        customer_count = 0
        customers = []

        for lead in converted_leads:
            if not Customer.objects.filter(lead=lead).exists():
                customer = Customer(
                    lead=lead,
                    account_manager=lead.assigned_to,
                    company=lead.company,
                    email=lead.email,
                    phone=lead.phone,
                    tier=random.choice(Customer.Tier.values),
                    lifetime_value=random.randint(5000, 500000),
                    customer_since=timezone.now() - timedelta(days=random.randint(1, 365)),
                )
                customers.append(customer)
                customer_count += 1

        Customer.objects.bulk_create(customers)
        self.stdout.write(self.style.SUCCESS(f'  {customer_count} customers created'))

        # ── Step 5: Create ActivityLogs ─────────────────────────
        self.stdout.write('Creating activity logs...')
        activity_types = ['call', 'email', 'meeting', 'note']
        subjects = {
            'call': ['Follow-up call', 'Discovery call', 'Demo call', 'Closing call'],
            'email': ['Intro email', 'Proposal sent', 'Follow-up email', 'Quote sent'],
            'meeting': ['Product demo', 'Initial meeting', 'Strategy session', 'Review meeting'],
            'note': ['Left voicemail', 'Contacted via LinkedIn', 'Referred by partner'],
        }

        activity_logs = []
        for lead in created_leads:
            num_activities = random.randint(1, 5)
            for _ in range(num_activities):
                atype = random.choice(activity_types)
                activity_logs.append(ActivityLog(
                    lead=lead,
                    performed_by=lead.assigned_to,
                    activity_type=atype,
                    subject=random.choice(subjects[atype]),
                    description=f'Activity log for {lead.full_name}',
                    occurred_at=timezone.now() - timedelta(days=random.randint(0, 60)),
                ))

        ActivityLog.objects.bulk_create(activity_logs)
        self.stdout.write(self.style.SUCCESS(f'  {len(activity_logs)} activities created'))

        # ── Step 6: Create SalesPipeline entries ────────────────
        self.stdout.write('Creating pipeline entries...')
        pipeline_entries = []
        pipeline_leads = Lead.objects.filter(status__in=['qualified', 'converted'])

        for lead in pipeline_leads:
            customer = Customer.objects.filter(lead=lead).first()
            pipeline_entries.append(SalesPipeline(
                lead=lead,
                customer=customer,
                owner=lead.assigned_to,
                stage=random.choice(SalesPipeline.Stage.values),
                deal_value=lead.estimated_value,
                probability=random.choice([10, 25, 50, 75, 90, 100]),
                expected_close_date=(
                    timezone.now() + timedelta(days=random.randint(7, 90))
                ).date(),
            ))

        SalesPipeline.objects.bulk_create(pipeline_entries)
        self.stdout.write(self.style.SUCCESS(f'  {len(pipeline_entries)} pipeline entries created'))

        # ── Summary ─────────────────────────────────────────────
        self.stdout.write('')
        self.stdout.write(self.style.SUCCESS('═' * 40))
        self.stdout.write(self.style.SUCCESS('  Seed complete!'))
        self.stdout.write(f'  Users      : {User.objects.filter(is_superuser=False).count()}')
        self.stdout.write(f'  Leads      : {Lead.objects.count()}')
        self.stdout.write(f'  Customers  : {Customer.objects.count()}')
        self.stdout.write(f'  Activities : {ActivityLog.objects.count()}')
        self.stdout.write(f'  Pipeline   : {SalesPipeline.objects.count()}')
        self.stdout.write(self.style.SUCCESS('═' * 40))