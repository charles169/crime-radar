import asyncio
import os
import re
import unittest
from datetime import datetime
from types import SimpleNamespace
from unittest import mock
from unittest.mock import AsyncMock

os.environ.setdefault(
    "CRIME_RADAR_DATABASE_URL",
    "mysql+asyncmy://test:test@127.0.0.1/test",
)
os.environ.setdefault("CRIME_RADAR_LOGIN_USERNAME", "test-operator")
os.environ.setdefault("CRIME_RADAR_LOGIN_PASSWORD", "test-password")

from fastapi import HTTPException
from fastapi.security import HTTPBasicCredentials

import backend.main as api
import public_reporting
from backend.complaints import demo_overlay_status, hash_tracking_code
from backend.models import (
    ComplaintActivity,
    ComplaintRecord,
    ComplaintStatusHistory,
    CrimeIncident,
)


class FakeScalars:
    def __init__(self, values):
        self.values = values

    def all(self):
        return self.values


class FakeSession:
    def __init__(self, complaint=None, history=None, activities=None):
        self.complaint = complaint
        self.history = list(history or [])
        self.activities = list(activities or [])
        self.added = []
        self.committed = False
        self.rolled_back = False

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        return False

    def add(self, item):
        self.added.append(item)
        if isinstance(item, ComplaintStatusHistory):
            self.history.append(item)
        if isinstance(item, ComplaintActivity):
            self.activities.append(item)
        if isinstance(item, ComplaintRecord):
            self.complaint = item

    async def flush(self):
        for item in self.added:
            if isinstance(item, CrimeIncident):
                item.id = 42

    async def commit(self):
        self.committed = True

    async def rollback(self):
        self.rolled_back = True

    async def get(self, model, key):
        if model is ComplaintRecord and self.complaint:
            return self.complaint if self.complaint.complaint_id == key else None
        return None

    async def scalar(self, _statement):
        return self.complaint

    async def scalars(self, _statement):
        entity = _statement.column_descriptions[0]["entity"]
        if entity is ComplaintActivity:
            return FakeScalars(self.activities)
        return FakeScalars(self.history)


class FakeOverlaySession:
    def __init__(self, rows):
        self.rows = rows

    async def execute(self, _statement):
        return FakeScalars(self.rows)


def make_request(path="/api/reports"):
    return public_reporting.Request(
        {
            "type": "http",
            "asgi": {"version": "3.0"},
            "http_version": "1.1",
            "method": "POST",
            "scheme": "http",
            "path": path,
            "raw_path": path.encode(),
            "query_string": b"",
            "headers": [],
            "client": ("127.0.0.1", 12345),
            "server": ("127.0.0.1", 8001),
            "root_path": "",
        }
    )


class ComplaintTrackingTests(unittest.TestCase):
    def test_submission_creates_id_code_hash_and_initial_history(self):
        session = FakeSession()
        report = public_reporting.PublicReportSubmission(
            incident_type="THEFT",
            latitude=13.0827,
            longitude=80.2707,
            turnstile_token="valid-turnstile-token",
        )
        with (
            mock.patch.object(public_reporting, "SessionLocal", return_value=session),
            mock.patch.object(
                public_reporting,
                "verify_turnstile",
                new=AsyncMock(return_value=True),
            ),
            mock.patch.object(public_reporting, "consume_rate_limit", return_value=None),
            mock.patch.object(public_reporting, "is_in_tamil_nadu", return_value=True),
        ):
            result = asyncio.run(
                public_reporting.submit_public_report(report, make_request())
            )

        self.assertRegex(result["complaint_id"], re.compile(r"^CR-[A-F0-9]{24}$"))
        self.assertEqual(result["complaint_status"], "Submitted")
        complaint = next(
            item for item in session.added if isinstance(item, ComplaintRecord)
        )
        self.assertEqual(
            complaint.tracking_token_hash,
            hash_tracking_code(result["tracking_code"]),
        )
        self.assertNotEqual(complaint.tracking_token_hash, result["tracking_code"])
        initial_update = next(
            item
            for item in session.added
            if isinstance(item, ComplaintStatusHistory)
        )
        self.assertEqual(initial_update.status, "Submitted")
        self.assertEqual(initial_update.updated_by, "Reporter")
        self.assertTrue(session.committed)

    def test_tracking_requires_the_private_code_and_returns_public_history(self):
        tracking_code = "private-code-for-complainant-only"
        updated_at = datetime(2026, 10, 17, 12, 0)
        complaint = ComplaintRecord(
            complaint_id="CR-ABCDEF0123456789ABCDEF01",
            incident_id=42,
            tracking_token_hash=hash_tracking_code(tracking_code),
            status="Under Review",
            submitted_at=updated_at,
            updated_at=updated_at,
            public_remarks="Your complaint is being reviewed.",
        )
        history = [
            ComplaintStatusHistory(
                id=1,
                complaint_id=complaint.complaint_id,
                status="Submitted",
                updated_at=updated_at,
                updated_by="Reporter",
                public_remarks="Complaint submitted for review.",
            ),
            ComplaintStatusHistory(
                id=2,
                complaint_id=complaint.complaint_id,
                status="Under Review",
                updated_at=updated_at,
                updated_by="test-operator",
                public_remarks=complaint.public_remarks,
            ),
        ]
        activity = ComplaintActivity(
            id=1,
            complaint_id=complaint.complaint_id,
            activity_type="SIMULATED_ALERT",
            occurred_at=updated_at,
            created_by="test-operator",
            station_name="Demo Area Station",
            message=(
                "SIMULATED ONLY — alert prepared, not sent. Status remains "
                "Under Review."
            ),
            simulated=True,
        )
        session = FakeSession(
            complaint=complaint,
            history=history,
            activities=[activity],
        )
        request_data = public_reporting.ComplaintTrackingRequest(
            complaint_id=complaint.complaint_id,
            tracking_code=tracking_code,
        )
        with (
            mock.patch.object(public_reporting, "SessionLocal", return_value=session),
            mock.patch.object(public_reporting, "consume_rate_limit", return_value=None),
        ):
            result = asyncio.run(
                public_reporting.track_complaint(request_data, make_request("/track"))
            )

        self.assertEqual(result["status"], "Under Review")
        self.assertEqual(len(result["history"]), 2)
        self.assertEqual(len(result["activities"]), 1)
        self.assertTrue(result["activities"][0]["simulated"])
        self.assertNotIn("created_by", result["activities"][0])
        self.assertNotIn("tracking_token_hash", result)
        self.assertNotIn("incident_id", result)
        self.assertNotIn("updated_by", result["history"][-1])

        wrong_code = public_reporting.ComplaintTrackingRequest(
            complaint_id=complaint.complaint_id,
            tracking_code="another-private-code-for-someone-else",
        )
        with (
            mock.patch.object(public_reporting, "SessionLocal", return_value=session),
            mock.patch.object(public_reporting, "consume_rate_limit", return_value=None),
            self.assertRaises(HTTPException) as error,
        ):
            asyncio.run(
                public_reporting.track_complaint(wrong_code, make_request("/track"))
            )
        self.assertEqual(error.exception.status_code, 404)
        self.assertTrue(error.exception.detail.startswith("Complaint not found"))

        missing_session = FakeSession()
        missing = public_reporting.ComplaintTrackingRequest(
            complaint_id="CR-111111111111111111111111",
            tracking_code=tracking_code,
        )
        with (
            mock.patch.object(
                public_reporting, "SessionLocal", return_value=missing_session
            ),
            mock.patch.object(public_reporting, "consume_rate_limit", return_value=None),
            self.assertRaises(HTTPException) as error,
        ):
            asyncio.run(
                public_reporting.track_complaint(missing, make_request("/track"))
            )
        self.assertEqual(error.exception.status_code, 404)
        self.assertTrue(error.exception.detail.startswith("Complaint not found"))

    def test_operator_authentication_and_status_audit(self):
        credentials = HTTPBasicCredentials(
            username=os.environ["CRIME_RADAR_LOGIN_USERNAME"],
            password=os.environ["CRIME_RADAR_LOGIN_PASSWORD"],
        )
        self.assertEqual(api.require_operator(credentials), credentials.username)
        with self.assertRaises(HTTPException) as error:
            api.require_operator(None)
        self.assertEqual(error.exception.status_code, 401)
        with self.assertRaises(HTTPException) as error:
            api.require_operator(
                HTTPBasicCredentials(username="intruder", password="incorrect")
            )
        self.assertEqual(error.exception.status_code, 401)

        now = datetime(2026, 10, 17, 12, 0)
        complaint = ComplaintRecord(
            complaint_id="CR-ABCDEF0123456789ABCDEF01",
            incident_id=42,
            tracking_token_hash=hash_tracking_code("test-code"),
            status="Submitted",
            submitted_at=now,
            updated_at=now,
        )
        session = FakeSession(complaint=complaint)
        update = api.ComplaintStatusUpdate(
            status="Under Review",
            public_remarks="The complaint is under review.",
        )
        result = asyncio.run(
            api.update_complaint_status(
                complaint.complaint_id,
                update,
                session,
                credentials.username,
            )
        )
        self.assertEqual(result["status"], "Under Review")
        self.assertEqual(session.history[-1].updated_by, credentials.username)
        self.assertEqual(
            session.history[-1].public_remarks,
            "The complaint is under review.",
        )
        self.assertTrue(session.committed)

    def test_incident_alert_status_uses_linked_complaint_record(self):
        updated_at = datetime(2026, 10, 17, 12, 0)
        complaint = ComplaintRecord(
            complaint_id="CR-ABCDEF0123456789ABCDEF01",
            incident_id=42,
            tracking_token_hash=hash_tracking_code("test-code"),
            status="Investigation in Progress",
            submitted_at=updated_at,
            updated_at=updated_at,
        )
        result = asyncio.run(
            api.get_incident_complaint_status("REPORT-TEST", FakeSession(complaint))
        )
        self.assertEqual(result["complaint_id"], complaint.complaint_id)
        self.assertEqual(result["status"], "Investigation in Progress")
        self.assertEqual(result["updated_at"], updated_at)

        with self.assertRaises(HTTPException) as error:
            asyncio.run(
                api.get_incident_complaint_status("NO-LINKED-COMPLAINT", FakeSession())
            )
        self.assertEqual(error.exception.status_code, 404)

    def test_demo_overlay_shows_existing_rows_without_changing_real_status(self):
        existing_rows = [
            SimpleNamespace(
                event_id="REPORT-EXISTING-001",
                incident_type="THEFT",
                timestamp=datetime(2026, 10, 17, 12, 0),
                complaint_id="CR-EXISTING-001",
                status="Under Review",
            ),
            SimpleNamespace(
                event_id="REPORT-EXISTING-002",
                incident_type="ROBBERY",
                timestamp=datetime(2026, 10, 16, 12, 0),
                complaint_id=None,
                status=None,
            ),
        ]
        result = asyncio.run(
            api.list_complaint_demo_overlay(
                FakeOverlaySession(existing_rows),
                "test-operator",
            )
        )

        self.assertEqual(len(result), 2)
        self.assertEqual(result[0]["incident_reference"], "REPORT-EXISTING-001")
        self.assertEqual(result[0]["recorded_status"], "Under Review")
        self.assertTrue(result[0]["demo_only"])
        self.assertIn(result[0]["demo_status"], api.COMPLAINT_STATUSES)
        self.assertEqual(
            result[0]["demo_status"],
            demo_overlay_status("CR-EXISTING-001"),
        )
        self.assertEqual(result[1]["recorded_status"], None)
        self.assertTrue(result[1]["demo_only"])
        self.assertEqual(existing_rows[0].status, "Under Review")

    def test_simulated_alert_is_persisted_without_changing_complaint_status(self):
        now = datetime(2026, 10, 17, 12, 0)
        complaint = ComplaintRecord(
            complaint_id="CR-ABCDEF0123456789ABCDEF01",
            incident_id=42,
            tracking_token_hash=hash_tracking_code("test-code"),
            status="Under Review",
            submitted_at=now,
            updated_at=now,
        )
        session = FakeSession(complaint=complaint)
        result = asyncio.run(
            api.record_simulated_complaint_alert(
                "REPORT-TEST",
                api.SimulatedComplaintAlert(station_name="Demo Area Station"),
                session,
                "test-operator",
            )
        )

        self.assertEqual(result["complaint_id"], complaint.complaint_id)
        self.assertEqual(result["status"], "Under Review")
        self.assertEqual(complaint.status, "Under Review")
        self.assertTrue(session.committed)
        activity = session.activities[0]
        self.assertEqual(activity.activity_type, "SIMULATED_ALERT")
        self.assertEqual(activity.created_by, "test-operator")
        self.assertEqual(activity.station_name, "Demo Area Station")
        self.assertTrue(activity.simulated)
        self.assertIn("not sent", activity.message)
        self.assertIn("status remains Under Review", activity.message)

    def test_complaint_management_routes_require_operator_authentication(self):
        protected_paths = {
            "/api/v1/complaints",
            "/api/v1/complaints/demo-overlay",
            "/api/v1/complaints/{complaint_id}",
            "/api/v1/incidents/{event_id}/complaint-status",
            "/api/v1/incidents/{event_id}/simulated-alert",
            "/api/v1/complaints/{complaint_id}/status",
        }
        routes = {
            route.path: route
            for route in api.app.routes
            if getattr(route, "path", None) in protected_paths
        }
        self.assertEqual(set(routes), protected_paths)
        for route in routes.values():
            self.assertIn(
                api.require_operator,
                [dependency.call for dependency in route.dependant.dependencies],
            )

    def test_rejection_requires_reason_and_status_cannot_move_backward(self):
        now = datetime(2026, 10, 17, 12, 0)
        complaint = ComplaintRecord(
            complaint_id="CR-ABCDEF0123456789ABCDEF01",
            incident_id=42,
            tracking_token_hash=hash_tracking_code("test-code"),
            status="Under Review",
            submitted_at=now,
            updated_at=now,
        )
        session = FakeSession(complaint=complaint)
        rejected = api.ComplaintStatusUpdate(status="Rejected")
        with self.assertRaises(HTTPException) as error:
            asyncio.run(
                api.update_complaint_status(
                    complaint.complaint_id, rejected, session, "operator"
                )
            )
        self.assertEqual(error.exception.status_code, 422)

        backward = api.ComplaintStatusUpdate(status="Submitted")
        with self.assertRaises(HTTPException) as error:
            asyncio.run(
                api.update_complaint_status(
                    complaint.complaint_id, backward, session, "operator"
                )
            )
        self.assertEqual(error.exception.status_code, 409)
        self.assertFalse(session.committed)


if __name__ == "__main__":
    unittest.main()
