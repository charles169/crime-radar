import asyncio
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from backend.complaints import hash_tracking_code
from backend.database import Base, SessionLocal, engine
from backend.models import (
    ComplaintRecord,
    ComplaintStatusHistory,
    CrimeIncident,
)
from seed_training_data import INCIDENT_LOCATIONS


DEMO_NOTICE = (
    "DEMO ONLY — synthetic workflow example. No real report, investigation, "
    "officer, or police action is represented."
)
DEMO_CASES = (
    ("Submitted", ("Submitted",)),
    ("Under Review", ("Submitted", "Under Review")),
    (
        "Assigned to Officer",
        ("Submitted", "Under Review", "Assigned to Officer"),
    ),
    (
        "Investigation in Progress",
        (
            "Submitted",
            "Under Review",
            "Assigned to Officer",
            "Investigation in Progress",
        ),
    ),
    (
        "Action Taken",
        (
            "Submitted",
            "Under Review",
            "Assigned to Officer",
            "Investigation in Progress",
            "Action Taken",
        ),
    ),
    (
        "Resolved",
        (
            "Submitted",
            "Under Review",
            "Assigned to Officer",
            "Investigation in Progress",
            "Action Taken",
            "Resolved",
        ),
    ),
    (
        "Closed",
        (
            "Submitted",
            "Under Review",
            "Assigned to Officer",
            "Investigation in Progress",
            "Action Taken",
            "Resolved",
            "Closed",
        ),
    ),
    ("Rejected", ("Submitted", "Under Review", "Rejected")),
)


async def seed_demo_complaints() -> None:
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)

        async with SessionLocal() as session:
            added = 0
            for index, (final_status, status_path) in enumerate(DEMO_CASES, start=1):
                complaint_id = f"CR-DEMO-{index:03d}"
                event_id = f"DEMO-COMPLAINT-EVENT-{index:03d}"
                incident = await session.scalar(
                    select(CrimeIncident).where(CrimeIncident.event_id == event_id)
                )
                if incident is None:
                    address, latitude, longitude = INCIDENT_LOCATIONS[index - 1]
                    incident = CrimeIncident(
                        event_id=event_id,
                        timestamp=now - timedelta(days=30 - index * 2),
                        status="SIMULATED DEMO",
                        priority="DEMO",
                        incident_type="DEMO COMPLAINT",
                        latitude=latitude,
                        longitude=longitude,
                        address=f"{address} (synthetic demo location)",
                        report_details=DEMO_NOTICE,
                    )
                    session.add(incident)
                    await session.flush()

                existing = await session.get(ComplaintRecord, complaint_id)
                if existing is not None:
                    continue

                submitted_at = now - timedelta(days=30 - index * 2)
                tracking_code = f"CRIME-RADAR-DEMO-TRACK-{index:03d}"
                complaint = ComplaintRecord(
                    complaint_id=complaint_id,
                    incident_id=incident.id,
                    tracking_token_hash=hash_tracking_code(tracking_code),
                    status=final_status,
                    submitted_at=submitted_at,
                    updated_at=submitted_at
                    + timedelta(days=max(0, len(status_path) - 1)),
                    public_remarks=DEMO_NOTICE,
                    rejection_reason=(
                        DEMO_NOTICE if final_status == "Rejected" else None
                    ),
                )
                session.add(complaint)
                for step, status in enumerate(status_path):
                    session.add(
                        ComplaintStatusHistory(
                            complaint_id=complaint_id,
                            status=status,
                            updated_at=submitted_at + timedelta(days=step),
                            updated_by="DEMO SYSTEM",
                            public_remarks=DEMO_NOTICE,
                            rejection_reason=(
                                DEMO_NOTICE if status == "Rejected" else None
                            ),
                        )
                    )
                added += 1

            await session.commit()

        print(
            f"Added {added} synthetic complaints (safe to rerun). "
            "Demo tracking credentials:"
        )
        for index, (status, _) in enumerate(DEMO_CASES, start=1):
            print(
                f"  CR-DEMO-{index:03d} / "
                f"CRIME-RADAR-DEMO-TRACK-{index:03d} — {status}"
            )
        print(DEMO_NOTICE)
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(seed_demo_complaints())
