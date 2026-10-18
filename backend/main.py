import hashlib
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from math import asin, ceil, cos, radians, sin, sqrt
from typing import List, Optional

from fastapi import Depends, FastAPI, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import inspect, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from .database import Base, SessionLocal, engine, get_db
from .geography import TAMIL_NADU_FEATURE, is_in_tamil_nadu
from .models import (
    CrimeIncident,
    IncidentClusterReview,
    PatrolUnit,
    PoliceStation,
    SourceSyncStatus,
)


@asynccontextmanager
async def lifespan(_: FastAPI):
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

        def ensure_report_details_column(sync_connection):
            columns = {
                column["name"]
                for column in inspect(sync_connection).get_columns("crime_incidents")
            }
            if "report_details" not in columns:
                sync_connection.exec_driver_sql(
                    "ALTER TABLE crime_incidents "
                    "ADD COLUMN report_details VARCHAR(1000) NULL"
                )
            if "display_after" not in columns:
                sync_connection.exec_driver_sql(
                    "ALTER TABLE crime_incidents "
                    "ADD COLUMN display_after DATETIME NULL"
                )

        await connection.run_sync(ensure_report_details_column)

    async with SessionLocal() as db:
        incidents = await db.scalars(select(CrimeIncident))
        for incident in incidents:
            if not is_in_tamil_nadu(incident.latitude, incident.longitude):
                await db.delete(incident)
        patrol_units = await db.scalars(select(PatrolUnit))
        for unit in patrol_units:
            if not is_in_tamil_nadu(unit.latitude, unit.longitude):
                await db.delete(unit)
        stations = await db.scalars(select(PoliceStation))
        for station in stations:
            if not is_in_tamil_nadu(station.latitude, station.longitude):
                await db.delete(station)
        source_statuses = await db.scalars(select(SourceSyncStatus))
        for status in source_statuses:
            await db.delete(status)
        await db.commit()
    yield
    await engine.dispose()

app = FastAPI(
    title="C.R.I.M.E. Radar API Core",
    description="Tamil Nadu-scoped incident and patrol telemetry ingestion API.",
    lifespan=lifespan,
)


class IncidentCreate(BaseModel):
    event_id: str = Field(min_length=1, max_length=100)
    status: str = Field(min_length=1, max_length=40)
    priority: str = Field(min_length=1, max_length=40)
    incident_type: str = Field(min_length=1, max_length=120)
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    address: str = Field(min_length=1, max_length=250)
    display_after: Optional[datetime] = None


class IncidentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    event_id: str
    timestamp: datetime
    status: str
    priority: str
    incident_type: str
    latitude: float
    longitude: float
    address: str
    report_details: Optional[str] = None


class PatrolUnitTelemetry(BaseModel):
    unit_id: str = Field(min_length=1, max_length=100)
    status: str = Field(min_length=1, max_length=40)
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)


class PatrolUnitRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    unit_id: str
    status: str
    latitude: float
    longitude: float
    updated_at: Optional[datetime] = None
    simulated: bool = False


class PoliceStationTelemetry(BaseModel):
    station_id: str = Field(min_length=1, max_length=100)
    name: str = Field(min_length=1, max_length=120)
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    unit_id: str = Field(min_length=1, max_length=100)


class PoliceStationRead(PoliceStationTelemetry):
    model_config = ConfigDict(from_attributes=True)


class ClusterReviewUpdate(BaseModel):
    status: str = Field(min_length=1, max_length=40)
    review_notes: Optional[str] = Field(default=None, max_length=1000)


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    lat1_rad = radians(lat1)
    lon1_rad = radians(lon1)
    lat2_rad = radians(lat2)
    lon2_rad = radians(lon2)
    delta_lat = lat2_rad - lat1_rad
    delta_lon = lon2_rad - lon1_rad
    a = (
        sin(delta_lat / 2) ** 2
        + cos(lat1_rad) * cos(lat2_rad) * sin(delta_lon / 2) ** 2
    )
    return 2 * 6371 * asin(sqrt(a))


def normalize_incident_type(value: Optional[str]) -> str:
    text = (value or "").strip().lower()
    if not text:
        return "uncategorized"
    aliases = {
        "assault": "assault",
        "violence": "assault",
        "attack": "assault",
        "robbery": "robbery",
        "theft": "theft",
        "burglary": "theft",
        "vehicle theft": "vehicle theft",
        "car theft": "vehicle theft",
        "auto theft": "vehicle theft",
        "snatching": "theft",
        "stolen vehicle": "vehicle theft",
        "harassment": "assault",
    }
    return aliases.get(text, text.replace("-", " "))


def retrieve_incident_similarity(incident_a, incident_b, radius_km: float, time_window_hours: float) -> tuple[float, list[str]]:
    reasons: list[str] = []
    lat_a, lon_a = float(incident_a.latitude), float(incident_a.longitude)
    lat_b, lon_b = float(incident_b.latitude), float(incident_b.longitude)
    distance_km = haversine_km(lat_a, lon_a, lat_b, lon_b)
    if distance_km > radius_km:
        return 0.0, reasons

    time_delta_hours = abs((incident_a.timestamp - incident_b.timestamp).total_seconds() / 3600)
    if time_delta_hours > time_window_hours:
        return 0.0, reasons

    type_a = normalize_incident_type(incident_a.incident_type)
    type_b = normalize_incident_type(incident_b.incident_type)
    type_score = 1.0 if type_a == type_b else 0.45 if type_a.split()[0] == type_b.split()[0] else 0.0
    if type_score <= 0:
        return 0.0, reasons

    reasons.append(
        f"Same or related category: {incident_a.incident_type} / {incident_b.incident_type}"
    )
    reasons.append(f"Reported within {time_delta_hours:.1f} hours")
    reasons.append(f"Within {distance_km:.1f} km of each other")

    detail_score = 0.0
    if incident_a.report_details and incident_b.report_details:
        words_a = set((incident_a.report_details or "").lower().split())
        words_b = set((incident_b.report_details or "").lower().split())
        if words_a and words_b:
            overlap = len(words_a & words_b) / max(len(words_a | words_b), 1)
            detail_score = overlap
            if overlap > 0.12:
                reasons.append("Shared descriptive details")

    score = (
        type_score * 0.55
        + max(1 - (time_delta_hours / max(time_window_hours, 1)), 0.0) * 0.2
        + min(distance_km / max(radius_km, 1), 1.0) * 0.15
        + detail_score * 0.1
    )
    return round(min(score, 1.0), 3), reasons


def cluster_incident_records(incidents: List[CrimeIncident], radius_km: float, time_window_hours: float, similarity_threshold: float, crime_type: Optional[str] = None):
    valid = []
    for incident in incidents:
        if incident.latitude is None or incident.longitude is None or incident.timestamp is None:
            continue
        if not is_in_tamil_nadu(float(incident.latitude), float(incident.longitude)):
            continue
        if crime_type and normalize_incident_type(incident.incident_type) != normalize_incident_type(crime_type):
            continue
        valid.append(incident)

    if len(valid) < 2:
        return []

    groups: List[List[CrimeIncident]] = []
    visited = set()
    for idx, incident in enumerate(valid):
        if idx in visited:
            continue
        cluster_members = [incident]
        visited.add(idx)
        for candidate_idx in range(idx + 1, len(valid)):
            if candidate_idx in visited:
                continue
            candidate = valid[candidate_idx]
            score, reasons = retrieve_incident_similarity(
                incident,
                candidate,
                radius_km=radius_km,
                time_window_hours=time_window_hours,
            )
            if score >= similarity_threshold and reasons:
                cluster_members.append(candidate)
                visited.add(candidate_idx)
        if len(cluster_members) > 1:
            groups.append(cluster_members)

    # Enforce the user review need: cluster only when incidents are within the
    # configured radius and the type/date similarity checks both pass.
    groups = [
        group for group in groups
        if len(group) > 1
        and all(
            retrieve_incident_similarity(group[0], member, radius_km, time_window_hours)[0]
            >= similarity_threshold
            for member in group[1:]
        )
    ]

    if not groups:
        return []

    clean_groups = []
    for group in groups:
        grouped_ids = {item.event_id for item in group}
        if len(grouped_ids) < 2:
            continue
        clean_groups.append(sorted(group, key=lambda item: item.timestamp, reverse=True))
    return clean_groups


def build_cluster_summary(group: List[CrimeIncident], cluster_id: str, review_status: str = "NEW"):
    event_ids = [item.event_id for item in group]
    cluster_latitude = sum(float(item.latitude) for item in group) / len(group)
    cluster_longitude = sum(float(item.longitude) for item in group) / len(group)
    timestamps = [item.timestamp for item in group if item.timestamp is not None]
    incident_types = [normalize_incident_type(item.incident_type) for item in group]
    primary_type = max(set(incident_types), key=incident_types.count)
    summary = {
        "cluster_id": cluster_id,
        "crime_type": primary_type.upper(),
        "incident_count": len(group),
        "review_status": review_status,
        "area": f"Lat {cluster_latitude:.4f}, Lon {cluster_longitude:.4f}",
        "centroid_latitude": round(cluster_latitude, 5),
        "centroid_longitude": round(cluster_longitude, 5),
        "start_date": min(timestamps).isoformat() if timestamps else None,
        "end_date": max(timestamps).isoformat() if timestamps else None,
        "incident_ids": event_ids,
        "incidents": [
            {
                "event_id": item.event_id,
                "timestamp": item.timestamp.isoformat() if item.timestamp else None,
                "latitude": float(item.latitude),
                "longitude": float(item.longitude),
                "incident_type": item.incident_type,
                "status": item.status,
                "priority": item.priority,
                "address": item.address,
                "report_details": item.report_details,
            }
            for item in group
        ],
    }
    return summary


@app.post("/api/v1/ingest", status_code=201, response_model=dict)
async def ingest_incident(
    incident: IncidentCreate,
    db: AsyncSession = Depends(get_db),
):
    if not is_in_tamil_nadu(incident.latitude, incident.longitude):
        raise HTTPException(
            status_code=422,
            detail="Incident coordinates are outside Tamil Nadu.",
        )
    existing = await db.scalar(
        select(CrimeIncident).where(CrimeIncident.event_id == incident.event_id)
    )
    if existing:
        raise HTTPException(status_code=409, detail="Incident event_id already exists.")

    db_incident = CrimeIncident(
        **incident.model_dump(),
        timestamp=datetime.utcnow(),
    )
    db.add(db_incident)
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(
            status_code=409,
            detail="Incident event_id already exists.",
        ) from exc
    await db.refresh(db_incident)
    return {"status": "success", "vector_id": db_incident.id}


@app.get("/api/v1/active-incidents", response_model=List[IncidentRead])
async def get_active_incidents(db: AsyncSession = Depends(get_db)):
    result = await db.scalars(
        select(CrimeIncident)
        .where(CrimeIncident.status != "CLEARED")
        .where(
            or_(
                CrimeIncident.display_after.is_(None),
                CrimeIncident.display_after <= datetime.utcnow(),
            )
        )
        .order_by(CrimeIncident.timestamp.desc())
    )
    return [
        incident
        for incident in result.all()
        if is_in_tamil_nadu(incident.latitude, incident.longitude)
    ]


@app.get("/api/v1/analytics/trends")
async def get_crime_trends(
    days: int = Query(default=30, ge=7, le=365),
    include_demo: bool = Query(default=False),
    db: AsyncSession = Depends(get_db),
):
    now = datetime.utcnow()
    today = now.date()
    current_start = datetime.combine(
        today - timedelta(days=days - 1), datetime.min.time()
    )
    comparison_start = current_start - timedelta(days=days)
    result = await db.scalars(
        select(CrimeIncident)
        .where(CrimeIncident.timestamp >= comparison_start)
        .where(
            CrimeIncident.timestamp
            < datetime.combine(today + timedelta(days=1), datetime.min.time())
        )
        .where(
            or_(
                CrimeIncident.display_after.is_(None),
                CrimeIncident.display_after <= now,
            )
        )
        .order_by(CrimeIncident.timestamp)
    )

    daily_counts = {}
    type_counts = {}
    priority_counts = {}
    current_count = 0
    previous_count = 0
    for incident in result:
        status = (incident.status or "").strip().upper()
        if not include_demo and status.startswith(
            ("SIMULATED DEMO", "TRAINING EXERCISE")
        ):
            continue
        if not is_in_tamil_nadu(incident.latitude, incident.longitude):
            continue

        is_current = incident.timestamp >= current_start
        period = "current" if is_current else "previous"
        current_count += int(is_current)
        previous_count += int(not is_current)
        incident_date = incident.timestamp.date().isoformat()
        daily_counts[incident_date] = daily_counts.get(incident_date, 0) + 1

        incident_type = (incident.incident_type or "Unspecified").strip()
        type_counts.setdefault(
            incident_type,
            {"incident_type": incident_type, "current_count": 0, "previous_count": 0},
        )[f"{period}_count"] += 1

        priority = (incident.priority or "Unspecified").strip()
        priority_counts.setdefault(
            priority,
            {"priority": priority, "current_count": 0, "previous_count": 0},
        )[f"{period}_count"] += 1

    type_rows = sorted(
        type_counts.values(),
        key=lambda item: (-item["current_count"], item["incident_type"].casefold()),
    )
    priority_rows = sorted(
        priority_counts.values(),
        key=lambda item: (-item["current_count"], item["priority"].casefold()),
    )
    current_days = [
        {
            "date": (today - timedelta(days=offset)).isoformat(),
            "count": daily_counts.get(
                (today - timedelta(days=offset)).isoformat(), 0
            ),
        }
        for offset in range(days - 1, -1, -1)
    ]
    spike_days = []
    spike_timeline = []
    for day in current_days:
        incident_day = datetime.fromisoformat(day["date"]).date()
        baseline_days = [
            daily_counts.get(
                (incident_day - timedelta(days=offset)).isoformat(), 0
            )
            for offset in range(1, 8)
        ]
        baseline_average = sum(baseline_days) / len(baseline_days)
        spike_threshold = max(
            3,
            ceil(baseline_average * 2),
            ceil(baseline_average + 3),
        )
        high_threshold = max(
            5,
            ceil(baseline_average * 3),
            ceil(baseline_average + 5),
        )
        spike_timeline.append(
            {
                **day,
                "baseline_average": round(baseline_average, 2),
                "spike_threshold": spike_threshold,
                "high_threshold": high_threshold,
            }
        )
        if day["count"] < spike_threshold:
            continue

        spike_days.append(
            {
                **day,
                "baseline_average": round(baseline_average, 2),
                "baseline_count": sum(baseline_days),
                "severity": "high" if day["count"] >= high_threshold else "elevated",
            }
        )
    busiest_day = max(current_days, key=lambda item: item["count"], default=None)
    change_percent = (
        round((current_count - previous_count) / previous_count * 100, 1)
        if previous_count
        else None
    )

    return {
        "days": days,
        "current_start": current_start.date().isoformat(),
        "current_end": today.isoformat(),
        "comparison_start": comparison_start.date().isoformat(),
        "comparison_end": (current_start - timedelta(days=1)).date().isoformat(),
        "current_count": current_count,
        "previous_count": previous_count,
        "change_percent": change_percent,
        "average_per_day": round(current_count / days, 2),
        "busiest_day": busiest_day,
        "include_demo": include_demo,
        "daily_counts": current_days,
        "spike_days": spike_days,
        "spike_timeline": spike_timeline,
        "spike_detection": {
            "baseline_days": 7,
            "minimum_reports": 3,
            "minimum_increase": 3,
            "minimum_multiple": 2,
        },
        "incident_types": type_rows,
        "priorities": priority_rows,
    }


@app.get("/api/v1/incident-clusters")
async def get_incident_clusters(
    crime_type: Optional[str] = Query(default=None),
    radius_km: float = Query(default=5.0, ge=0.5, le=50.0),
    time_window_hours: float = Query(default=24.0, ge=1.0, le=168.0),
    similarity_threshold: float = Query(default=0.55, ge=0.1, le=1.0),
    review_status: Optional[str] = Query(default=None),
    db: AsyncSession = Depends(get_db),
):
    result = await db.scalars(
        select(CrimeIncident)
        .where(CrimeIncident.status != "CLEARED")
        .where(
            or_(
                CrimeIncident.display_after.is_(None),
                CrimeIncident.display_after <= datetime.utcnow(),
            )
        )
        .order_by(CrimeIncident.timestamp.desc())
    )
    incidents = [incident for incident in result.all() if is_in_tamil_nadu(float(incident.latitude), float(incident.longitude))]
    if not incidents:
        return {"clusters": [], "demo_mode": True, "message": "No incident records are available in the connected MySQL database."}

    cluster_groups = cluster_incident_records(
        incidents=incidents,
        radius_km=radius_km,
        time_window_hours=time_window_hours,
        similarity_threshold=similarity_threshold,
        crime_type=crime_type,
    )

    clusters = []
    for index, group in enumerate(cluster_groups, start=1):
        cluster_id_seed = ",".join(sorted(item.event_id for item in group))
        cluster_id = "CL-" + hashlib.sha256(cluster_id_seed.encode("utf-8")).hexdigest()[:12].upper()
        cluster_review = await db.get(IncidentClusterReview, cluster_id)
        review_status_value = cluster_review.review_status if cluster_review else "NEW"
        if review_status and review_status_value.lower() != review_status.lower():
            continue
        cluster_summary = build_cluster_summary(group, cluster_id, review_status_value)
        reasons = []
        for idx, incident in enumerate(group[:-1]):
            for other in group[idx + 1 :]:
                score, item_reasons = retrieve_incident_similarity(
                    incident,
                    other,
                    radius_km=radius_km,
                    time_window_hours=time_window_hours,
                )
                if score >= similarity_threshold and item_reasons:
                    reasons.append(
                        {
                            "event_ids": [incident.event_id, other.event_id],
                            "score": score,
                            "reasons": item_reasons,
                        }
                    )
        cluster_summary["reasons"] = reasons[:8]
        cluster_summary["area"] = f"{cluster_summary['centroid_latitude']:.4f}, {cluster_summary['centroid_longitude']:.4f}"
        cluster_summary["radius_km"] = radius_km
        cluster_summary["time_window_hours"] = time_window_hours
        cluster_summary["similarity_threshold"] = similarity_threshold
        clusters.append(cluster_summary)

    clusters.sort(key=lambda item: (-item["incident_count"], item["cluster_id"]))
    return {
        "clusters": clusters,
        "demo_mode": False,
        "total_incidents": len(incidents),
        "total_clusters": len(clusters),
    }


@app.get("/api/v1/incident-clusters/{cluster_id}")
async def get_incident_cluster_detail(
    cluster_id: str,
    radius_km: float = Query(default=5.0, ge=0.5, le=50.0),
    time_window_hours: float = Query(default=24.0, ge=1.0, le=168.0),
    similarity_threshold: float = Query(default=0.55, ge=0.1, le=1.0),
    db: AsyncSession = Depends(get_db),
):
    result = await db.scalars(
        select(CrimeIncident)
        .where(CrimeIncident.status != "CLEARED")
        .where(
            or_(
                CrimeIncident.display_after.is_(None),
                CrimeIncident.display_after <= datetime.utcnow(),
            )
        )
        .order_by(CrimeIncident.timestamp.desc())
    )
    incidents = [incident for incident in result.all() if is_in_tamil_nadu(float(incident.latitude), float(incident.longitude))]
    groups = cluster_incident_records(
        incidents=incidents,
        radius_km=radius_km,
        time_window_hours=time_window_hours,
        similarity_threshold=similarity_threshold,
    )
    for group in groups:
        candidate_id = "CL-" + hashlib.sha256(
            ",".join(sorted(item.event_id for item in group)).encode("utf-8")
        ).hexdigest()[:12].upper()
        if candidate_id == cluster_id:
            review = await db.get(IncidentClusterReview, cluster_id)
            cluster_summary = build_cluster_summary(group, cluster_id, review.review_status if review else "NEW")
            return {
                "cluster": cluster_summary,
                "demo_mode": False,
            }
    raise HTTPException(status_code=404, detail="Cluster not found.")


@app.post("/api/v1/incident-clusters/{cluster_id}/review")
async def update_incident_cluster_review(
    cluster_id: str,
    review: ClusterReviewUpdate,
    db: AsyncSession = Depends(get_db),
):
    allowed_statuses = {"NEW", "UNDER_REVIEW", "REVIEWED", "NEEDS_FURTHER_INVESTIGATION"}
    normalized_status = review.status.strip().upper()
    if normalized_status not in allowed_statuses:
        raise HTTPException(status_code=422, detail="Unsupported review status.")

    row = await db.get(IncidentClusterReview, cluster_id)
    if row is None:
        row = IncidentClusterReview(
            cluster_id=cluster_id,
            review_status=normalized_status,
            review_notes=review.review_notes,
            updated_at=datetime.utcnow(),
            cluster_summary=f"Review updated to {normalized_status}",
        )
        db.add(row)
    else:
        row.review_status = normalized_status
        row.review_notes = review.review_notes
        row.updated_at = datetime.utcnow()
        row.cluster_summary = f"Review updated to {normalized_status}"

    await db.commit()
    await db.refresh(row)
    return {
        "cluster_id": row.cluster_id,
        "review_status": row.review_status,
        "review_notes": row.review_notes,
        "updated_at": row.updated_at.isoformat(),
    }


@app.get("/api/v1/sources")
async def get_data_sources():
    return [
        {
            "source_id": "tamil_nadu_agency_webhooks",
            "name": "Tamil Nadu-scoped agency telemetry",
            "url": "/docs",
            "jurisdiction": "Tamil Nadu, India",
            "boundary_source": "geoBoundaries India ADM1 · Tamil Nadu",
            "boundary_url": "https://www.geoboundaries.org/",
            "boundary_license": "CC BY 2.5 IN",
            "automated_public_feed": False,
            "last_success": None,
            "records_loaded": None,
            "data_through": None,
            "error": None,
            "disclaimer": (
                "Only reports inside Tamil Nadu are accepted. No Tamil Nadu Police "
                "CAD/911 or patrol GPS system is connected; live records require "
                "an authorized agency to send data to the documented webhook."
            ),
        }
    ]


@app.get("/api/v1/jurisdiction")
async def get_jurisdiction():
    return TAMIL_NADU_FEATURE


@app.post("/api/v1/police-stations", response_model=PoliceStationRead)
async def upsert_police_station(
    station: PoliceStationTelemetry,
    db: AsyncSession = Depends(get_db),
):
    if not is_in_tamil_nadu(station.latitude, station.longitude):
        raise HTTPException(
            status_code=422,
            detail="Station coordinates are outside Tamil Nadu.",
        )
    db_station = await db.get(PoliceStation, station.station_id)
    if db_station is None:
        db_station = PoliceStation(**station.model_dump())
        db.add(db_station)
    else:
        for field, value in station.model_dump(exclude={"station_id"}).items():
            setattr(db_station, field, value)
    await db.commit()
    await db.refresh(db_station)
    return db_station


@app.get("/api/v1/police-stations", response_model=List[PoliceStationRead])
async def get_police_stations(db: AsyncSession = Depends(get_db)):
    result = await db.scalars(select(PoliceStation).order_by(PoliceStation.name))
    return [
        station
        for station in result.all()
        if is_in_tamil_nadu(station.latitude, station.longitude)
    ]


@app.post("/api/v1/patrol-units", response_model=PatrolUnitRead)
async def ingest_patrol_unit(
    unit: PatrolUnitTelemetry,
    db: AsyncSession = Depends(get_db),
):
    if not is_in_tamil_nadu(unit.latitude, unit.longitude):
        raise HTTPException(
            status_code=422,
            detail="Patrol coordinates are outside Tamil Nadu.",
        )
    db_unit = await db.get(PatrolUnit, unit.unit_id)
    if db_unit is None:
        db_unit = PatrolUnit(unit_id=unit.unit_id, **unit.model_dump(exclude={"unit_id"}))
        db.add(db_unit)
    else:
        for field, value in unit.model_dump(exclude={"unit_id"}).items():
            setattr(db_unit, field, value)
        db_unit.updated_at = datetime.utcnow()
    await db.commit()
    await db.refresh(db_unit)
    return db_unit


@app.get("/api/v1/patrol-units", response_model=List[PatrolUnitRead])
async def get_live_patrol_units(
    lat: Optional[float] = Query(default=None, ge=-90, le=90),
    lon: Optional[float] = Query(default=None, ge=-180, le=180),
    db: AsyncSession = Depends(get_db),
):
    if (lat is None) != (lon is None):
        raise HTTPException(status_code=422, detail="Provide both lat and lon coordinates.")

    result = await db.scalars(
        select(PatrolUnit)
        .where(PatrolUnit.updated_at >= datetime.utcnow() - timedelta(minutes=2))
        .order_by(PatrolUnit.unit_id)
    )
    return [
        unit
        for unit in result.all()
        if is_in_tamil_nadu(unit.latitude, unit.longitude)
    ]
