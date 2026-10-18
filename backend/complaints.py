import hashlib

from .models import ComplaintActivity, ComplaintRecord, ComplaintStatusHistory


COMPLAINT_STATUSES = (
    "Submitted",
    "Under Review",
    "Assigned to Officer",
    "Investigation in Progress",
    "Action Taken",
    "Resolved",
    "Closed",
    "Rejected",
)


def hash_tracking_code(code: str) -> str:
    return hashlib.sha256(code.encode("utf-8")).hexdigest()


def demo_overlay_status(record_key: str) -> str:
    digest = hashlib.sha256(record_key.encode("utf-8")).digest()
    return COMPLAINT_STATUSES[int.from_bytes(digest[:4], "big") % len(COMPLAINT_STATUSES)]


def complaint_detail_payload(
    complaint: ComplaintRecord,
    history: list[ComplaintStatusHistory],
    activities: list[ComplaintActivity] | None = None,
) -> dict:
    public_fields = (
        "department",
        "assigned_officer",
        "action_taken",
        "public_remarks",
        "next_steps",
        "rejection_reason",
    )
    return {
        "complaint_id": complaint.complaint_id,
        "submitted_at": complaint.submitted_at,
        "status": complaint.status,
        "updated_at": complaint.updated_at,
        **{field: getattr(complaint, field) for field in public_fields},
        "history": [
            {
                "status": entry.status,
                "updated_at": entry.updated_at,
                **{field: getattr(entry, field) for field in public_fields},
            }
            for entry in history
        ],
        "activities": [
            {
                "activity_type": activity.activity_type,
                "occurred_at": activity.occurred_at,
                "station_name": activity.station_name,
                "message": activity.message,
                "simulated": activity.simulated,
            }
            for activity in (activities or [])
        ],
        "is_demo": complaint.complaint_id.startswith("CR-DEMO-"),
    }
