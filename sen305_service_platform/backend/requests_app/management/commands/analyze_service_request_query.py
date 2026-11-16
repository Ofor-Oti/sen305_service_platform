from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.utils import timezone

from requests_app.models import Category, ServiceRequest


class Command(BaseCommand):
    help = "Create synthetic service requests and print SQL/EXPLAIN for the lab query."

    def handle(self, *args, **options):
        User = get_user_model()
        requester, _ = User.objects.get_or_create(username="sen305_lab_requester")
        network, _ = Category.objects.get_or_create(
            name="Synthetic Network", defaults={"description": "Synthetic lab data only."}
        )
        facilities, _ = Category.objects.get_or_create(
            name="Synthetic Facilities", defaults={"description": "Synthetic lab data only."}
        )

        statuses = [
            ServiceRequest.Status.OPEN,
            ServiceRequest.Status.ASSIGNED,
            ServiceRequest.Status.IN_PROGRESS,
        ]
        now = timezone.now()
        # Twelve deterministic synthetic rows: two categories and three statuses.
        for category_number, category in enumerate((network, facilities)):
            for number in range(6):
                status = statuses[number % len(statuses)]
                due_at = now + timedelta(days=(number - 2))
                ServiceRequest.objects.update_or_create(
                    title=f"SEN305 synthetic {category_number + 1}-{number + 1}",
                    defaults={
                        "requester": requester,
                        "category": category,
                        "description": "Synthetic data created for the SEN305 query-analysis exercise.",
                        "location": "Synthetic Lab",
                        "priority": (number % 5) + 1,
                        "status": status,
                        "due_at": due_at,
                    },
                )

        queryset = ServiceRequest.objects.filter(
            category=network,
            status__in=(ServiceRequest.Status.OPEN, ServiceRequest.Status.ASSIGNED),
        ).order_by("priority", "created_at")

        self.stdout.write(self.style.SUCCESS("Synthetic records ready (12 total across two categories)."))
        self.stdout.write("\nGenerated SQL:")
        self.stdout.write(str(queryset.query))
        self.stdout.write("\nQuery execution plan:")
        try:
            self.stdout.write(queryset.explain())
        except Exception as exc:
            self.stdout.write(self.style.WARNING(f"EXPLAIN could not be run: {exc}"))
        self.stdout.write(
            "\nNote: with this deliberately small synthetic dataset, MySQL may choose a table scan "
            "instead of an index. Record the actual EXPLAIN output and explain that cost-based choice; "
            "do not claim an index was used unless the plan says so."
        )
        self.stdout.write(f"\nMatching rows: {queryset.count()}")
