from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models import ProtectedError
from django.test import TestCase

from .models import Category, ServiceRequest, WorkOrder


class ServiceRequestModelTests(TestCase):
    def setUp(self):
        user_model = get_user_model()
        self.requester = user_model.objects.create_user(username="requester")
        self.technician = user_model.objects.create_user(username="technician")
        self.category = Category.objects.create(name="Electrical")

    def make_request(self, **overrides):
        values = {
            "requester": self.requester,
            "category": self.category,
            "title": "Faulty socket",
            "description": "Socket does not supply power.",
            "location": "Software Engineering Lab",
            "priority": 2,
        }
        values.update(overrides)
        return ServiceRequest.objects.create(**values)

    def test_default_status_is_open(self):
        item = self.make_request()
        self.assertEqual(item.status, ServiceRequest.Status.OPEN)

    def test_priority_validator_rejects_zero(self):
        item = ServiceRequest(
            requester=self.requester,
            category=self.category,
            title="Invalid",
            description="Invalid priority.",
            location="Lab",
            priority=0,
        )
        with self.assertRaises(ValidationError):
            item.full_clean()

    def test_database_constraint_rejects_priority_six(self):
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                self.make_request(priority=6)

    def test_category_in_use_is_protected(self):
        self.make_request()
        with self.assertRaises(ProtectedError):
            self.category.delete()

    def test_request_accepts_only_one_work_order(self):
        item = self.make_request()
        WorkOrder.objects.create(
            service_request=item,
            technician=self.technician,
        )
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                WorkOrder.objects.create(
                    service_request=item,
                    technician=self.technician,
                )


class ServiceRequestExtensionTests(TestCase):
    def setUp(self):
        user_model = get_user_model()
        self.requester = user_model.objects.create_user(username="extension_requester")
        self.category = Category.objects.create(name="Network")

    def make_request(self, **overrides):
        values = {
            "requester": self.requester,
            "category": self.category,
            "title": "Network outage",
            "description": "Synthetic laboratory request.",
            "location": "Computer Lab",
            "priority": 2,
        }
        values.update(overrides)
        return ServiceRequest(**values)

    def test_due_at_is_nullable(self):
        item = self.make_request()
        item.full_clean()
        item.save()
        self.assertIsNone(item.due_at)

    def test_status_due_date_index_is_declared(self):
        index_names = {index.name for index in ServiceRequest._meta.indexes}
        self.assertIn("req_status_due_idx", index_names)

    def test_due_before_query_returns_only_earlier_due_requests(self):
        from datetime import timedelta
        from django.utils import timezone

        cutoff = timezone.now()
        overdue = self.make_request(due_at=cutoff - timedelta(hours=1))
        overdue.save()
        future = self.make_request(due_at=cutoff + timedelta(hours=1), title="Future request")
        future.save()
        results = ServiceRequest.objects.filter(due_at__lt=cutoff)
        self.assertEqual(list(results), [overdue])

    def test_resolved_request_requires_resolved_at(self):
        item = self.make_request(
            status=ServiceRequest.Status.RESOLVED,
            resolution_summary="Replaced faulty network cable.",
        )
        with self.assertRaises(ValidationError) as context:
            item.full_clean()
        self.assertIn("resolved_at", context.exception.message_dict)

    def test_resolved_request_requires_nonempty_summary(self):
        from django.utils import timezone

        item = self.make_request(
            status=ServiceRequest.Status.RESOLVED,
            resolved_at=timezone.now(),
            resolution_summary="   ",
        )
        with self.assertRaises(ValidationError) as context:
            item.full_clean()
        self.assertIn("resolution_summary", context.exception.message_dict)

    def test_closed_request_requires_both_resolution_fields(self):
        item = self.make_request(status=ServiceRequest.Status.CLOSED)
        with self.assertRaises(ValidationError) as context:
            item.full_clean()
        self.assertIn("resolved_at", context.exception.message_dict)
        self.assertIn("resolution_summary", context.exception.message_dict)

    def test_resolved_request_with_resolution_details_passes_full_clean(self):
        from django.utils import timezone

        item = self.make_request(
            status=ServiceRequest.Status.RESOLVED,
            resolved_at=timezone.now(),
            resolution_summary="Replaced the damaged network cable and verified connectivity.",
        )
        item.full_clean()  # Must not raise.

    def test_open_request_does_not_require_resolution_details(self):
        item = self.make_request(status=ServiceRequest.Status.OPEN)
        item.full_clean()  # Must not raise.
