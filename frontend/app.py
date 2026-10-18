import asyncio
import hashlib
import hmac
import html
import json
import os
import re
import time
from datetime import datetime, timedelta, timezone
from math import asin, atan2, ceil, cos, degrees, floor, radians, sin, sqrt
from pathlib import Path

import folium
import pandas as pd
import requests
import streamlit as st
import streamlit.components.v1 as components
from branca.element import MacroElement, Template
from dotenv import load_dotenv
from folium.plugins import HeatMap

def load_login_credentials():
    env_path = Path(__file__).resolve().parents[1] / ".env"
    if env_path.exists():
        load_dotenv(env_path, override=False)
    username = os.getenv("CRIME_RADAR_LOGIN_USERNAME", "").strip()
    password = os.getenv("CRIME_RADAR_LOGIN_PASSWORD", "").strip()
    return username, password

LOGIN_USERNAME, LOGIN_PASSWORD = load_login_credentials()

with (Path(__file__).resolve().parents[1] / "backend" / "data" / "tamil_nadu.geojson").open(
    encoding="utf-8"
) as boundary_file:
    TAMIL_NADU_FEATURE = json.load(boundary_file)


class TacticalTileStyle(MacroElement):
    _template = Template(
        """{% macro html(this, kwargs) %}
        <style>.leaflet-container {
            background:#040b16;
            border:1px solid rgba(116,190,255,.18);
            border-radius:16px;
            box-shadow:inset 0 0 0 1px rgba(94,176,255,.12), 0 18px 32px rgba(0,0,0,.22);
            font-family:Arial,sans-serif;
        }
        .leaflet-control-zoom,
        .leaflet-control-layers,
        .leaflet-control-attribution {
            background:rgba(7,17,29,.82) !important;
            border:1px solid rgba(110,175,255,.28) !important;
            border-radius:10px !important;
            color:#dfeef8 !important;
            box-shadow:0 12px 22px rgba(2,7,12,.35);
        }
        .leaflet-control-zoom a,
        .leaflet-control-layers-toggle {
            background:rgba(10,28,44,.94) !important;
            color:#dfeef8 !important;
            border-bottom:1px solid rgba(110,175,255,.2) !important;
        }
        .leaflet-control-attribution,
        .leaflet-control-attribution a {
            color:#c9d9ea !important;
            font-size:10px;
        }
        .leaflet-heatmap-layer {filter:drop-shadow(0 0 9px rgba(255,98,42,.6));}
        .leaflet-fade-anim .leaflet-tile,
        .leaflet-fade-anim .leaflet-popup {transition:none !important;}
        .incident-cluster-icon {align-items:center;background:#35151c;
            border:2px solid #ff5364;border-radius:50%;box-shadow:0 0 10px #ff354d66;
            display:flex;height:34px;justify-content:center;width:34px;}
        .incident-cluster-dot {background:#ff354d;border:2px solid #fff;
            border-radius:50%;box-shadow:0 0 8px #ff354d99;height:12px;width:12px;}
        .incident-map-marker {background:#ff354d;border:2px solid #fff;
            border-radius:50%;box-shadow:0 0 8px #ff354d99;height:12px;
            position:relative;width:12px;}
        .incident-map-marker::after {background:#fff;border-radius:50%;content:"";
            height:4px;left:50%;position:absolute;top:50%;
            transform:translate(-50%,-50%);width:4px;}
        .incident-map-marker.selected {background:#ff354d;border:3px solid #fff;
            box-shadow:0 0 12px #ff354d;}
        .selected-incident-target {position:relative;width:30px;height:30px;
            background:#ff354d;border:4px solid #fff;border-radius:50%;
            box-shadow:0 0 0 7px #ff354d55,0 0 20px 8px #ff354dcc;}
        .selected-incident-target::after {position:absolute;content:"";
            inset:7px;background:#fff;border-radius:50%;}
        .leaflet-popup-content-wrapper {background:rgba(5,16,28,.94);
            border:1px solid #2b8bc4;border-radius:10px;
            box-shadow:0 0 18px rgba(20,190,220,.2);color:#d7eaf1;}
        .leaflet-popup-content {margin:0;max-width:310px;width: min(310px, 72vw);}
        .leaflet-popup-tip {background:rgba(5,16,28,.94);border:1px solid #2b8bc4;}
        .leaflet-popup-close-button {color:#66d8e9 !important;}
        .incident-hud-content {color:#d7eaf1;font-family:Arial,sans-serif;
            padding:12px;}
        .incident-hud-kicker {color:#59d6e8;font-size:10px;font-weight:700;
            letter-spacing:1.5px;text-transform:uppercase;}
        .incident-hud-title {color:#effaff;font-size:16px;font-weight:700;
            line-height:1.25;margin:5px 0 10px;overflow-wrap:anywhere;}
        .incident-hud-grid {display:grid;grid-template-columns:1fr 1fr;gap:7px;}
        .incident-hud-field {background:#0b2437;border-left:2px solid #197b91;
            min-width:0;padding:6px 8px;}
        .incident-hud-field-wide {grid-column:1/-1;}
        .incident-hud-label {color:#70aabc;display:block;font-size:9px;
            font-weight:700;letter-spacing:1px;text-transform:uppercase;}
        .incident-hud-value {color:#e0f1f5;display:block;font-size:12px;
            line-height:1.4;margin-top:3px;overflow-wrap:anywhere;}
        .incident-hud-state {display:flex;flex-wrap:wrap;gap:6px;margin-top:9px;}
        .incident-hud-state span {background:#102d40;border:1px solid #22677c;
            border-radius:3px;color:#89e5ef;font-size:9px;font-weight:700;
            letter-spacing:.7px;padding:3px 6px;}
        .incident-hud-report,.incident-hud-extra {border-top:1px solid #174054;
            color:#a8cbd5;font-size:11px;line-height:1.5;margin-top:9px;
            padding-top:8px;overflow-wrap:anywhere;}
        .police-station-badge {align-items:center;background:#0756a0;
            border:2px solid #fff;clip-path:polygon(50% 0,95% 15%,88% 65%,
            50% 100%,12% 65%,5% 15%);color:#fff;display:flex;
            flex-direction:column;gap:0;
            filter:drop-shadow(0 0 5px #168bd2);font:700 9px Arial,sans-serif;
            height:38px;justify-content:center;width:36px;
            text-shadow:0 1px 3px #001a33;}
        .police-station-star {font-size:15px;line-height:15px;}
        </style>
        {% endmacro %}"""
    )


class MapLegendControl(MacroElement):
    _template = Template(
        """{% macro script(this, kwargs) %}
        (function () {
          const control = L.control({position: "topright"});
          control.onAdd = function () {
            const element = L.DomUtil.create("div", "radar-map-legend");
            element.setAttribute("role", "group");
            element.setAttribute("aria-label", "Map legend");
            element.innerHTML =
              '<div class="radar-map-legend-title">MAP KEY</div>' +
              '<div class="radar-map-legend-row"><span class="radar-map-legend-symbol">' +
              '<i class="radar-legend-incident"></i></span>Reported incident</div>' +
              '<div class="radar-map-legend-row"><span class="radar-map-legend-symbol">' +
              '<i class="radar-legend-critical"></i></span>Critical priority</div>' +
              '<div class="radar-map-legend-row"><span class="radar-map-legend-symbol">' +
              '<i class="radar-legend-station">PD</i></span>Police station</div>' +
              '<div class="radar-map-legend-row"><span class="radar-map-legend-symbol">' +
              '<i class="radar-legend-unit"></i></span>Patrol unit</div>' +
              '<div class="radar-map-legend-row"><span class="radar-map-legend-symbol">' +
              '<i class="radar-legend-patrol"></i></span>Patrol route</div>' +
              '<div class="radar-map-legend-row"><span class="radar-map-legend-symbol">' +
              '<i class="radar-legend-boundary"></i></span>Tamil Nadu boundary</div>';
            L.DomEvent.disableClickPropagation(element);
            L.DomEvent.disableScrollPropagation(element);
            return element;
          };
          control.addTo({{this._parent.get_name()}});
        })();
        {% endmacro %}"""
    )


class MapFocusWatcher(MacroElement):
    _template = Template(
        """{% macro script(this, kwargs) %}
        (function () {
          const map = {{this._parent.get_name()}};
          const city = {{this.city_json}};
          const homeCenter = {{this.home_center_json}};
          const homeZoom = {{this.home_zoom}};
          const minimumZoom = {{this.minimum_zoom}};
          const jurisdictionBounds = L.latLngBounds({{this.bounds_json}});
          map.setMinZoom(minimumZoom);
          map.setMaxBounds(jurisdictionBounds);
          map.options.maxBoundsViscosity = 1.0;
          map.on("zoomend", function () {
            if (map.getZoom() < minimumZoom) {
              map.setZoom(minimumZoom, {animate: false});
            }
          });
          const viewKey = "crime-radar-map-view";
          const savedView = window.parent.sessionStorage.getItem(viewKey);
          if (savedView) {
            const view = JSON.parse(savedView);
            if (view.city === city) {
              map.setView(view.center, Math.max(view.zoom, minimumZoom), {
                animate: false
              });
            } else {
              map.setView(homeCenter, homeZoom, {animate: false});
            }
          } else {
            map.setView(homeCenter, homeZoom, {animate: false});
          }
          map.on("moveend", function () {
            window.parent.sessionStorage.setItem(viewKey, JSON.stringify({
              city: city,
              center: map.getCenter(),
              zoom: map.getZoom()
            }));
          });
          const selectionLayer = L.layerGroup().addTo(map);
          let lastSelection = null;
          let viewBeforeSelection = null;
          const syncMapState = function () {
            const rawSelection =
              window.parent.sessionStorage.getItem("crime-radar-map-selection") || "null";
            if (rawSelection === lastSelection) return;
            lastSelection = rawSelection;
            const hadSelection = Boolean(viewBeforeSelection);
            selectionLayer.clearLayers();
            const selection = JSON.parse(rawSelection);
            if (!selection || !selection.incident) {
              if (viewBeforeSelection) {
                map.flyTo(viewBeforeSelection.center, viewBeforeSelection.zoom, {
                  animate: true,
                  duration: 1.1,
                  easeLinearity: 0.2
                });
                viewBeforeSelection = null;
              }
              return;
            }
            if (!hadSelection) {
              viewBeforeSelection = {
                center: map.getCenter(),
                zoom: map.getZoom()
              };
            }

            const incident = selection.incident;
            const incidentMarker = L.marker(
              [incident.latitude, incident.longitude],
              {
                icon: L.divIcon({
                  className: "",
                  html: '<div class="selected-incident-target"></div>',
                  iconSize: [38, 38],
                  iconAnchor: [19, 19]
                }),
                title: "Selected incident location"
              }
            ).bindPopup(incident.popup_html);
            selectionLayer.addLayer(incidentMarker);

            const focusPoints = [[incident.latitude, incident.longitude]];
            selection.stations.forEach(function (station) {
              const marker = L.marker(
                [station.latitude, station.longitude],
                {
                  icon: L.divIcon({
                    className: "",
                    html: '<div class="police-station-badge">' +
                      '<span class="police-station-star">★</span>' +
                      '<span>PD</span></div>',
                    iconSize: [42, 46],
                    iconAnchor: [21, 23]
                  }),
                  title: station.name
                }
              ).bindPopup(station.popup_html);
              selectionLayer.addLayer(marker);
              focusPoints.push([station.latitude, station.longitude]);
            });
            map.flyToBounds(L.latLngBounds(focusPoints), {
              animate: true,
              duration: 1.35,
              easeLinearity: 0.16,
              padding: [64, 64],
              maxZoom: 14
            });
            map.once("moveend", function () {
              incidentMarker.openPopup();
            });
          };
          window.parent.document.addEventListener(
            "crime-radar-map-update",
            syncMapState
          );
          syncMapState();
          window.setInterval(syncMapState, 250);
        })();
        {% endmacro %}"""
    )

    def __init__(
        self,
        city,
        home_center,
        home_zoom,
        minimum_zoom,
        jurisdiction_bounds,
    ):
        super().__init__()
        self._name = "MapFocusWatcher"
        self.city_json = json.dumps(city)
        self.home_center_json = json.dumps(home_center)
        self.home_zoom = home_zoom
        self.minimum_zoom = minimum_zoom
        self.bounds_json = json.dumps(jurisdiction_bounds)


st.set_page_config(
    layout="wide",
    page_title="C.R.I.M.E. Radar | Tamil Nadu",
    page_icon="📡",
    initial_sidebar_state="collapsed",
)


def render_login_page():
    st.markdown(
        """
        <style>
        [data-testid="stMainBlockContainer"] {
            max-width: 1120px;
            padding-top: 5vh;
        }
        .login-brand {
            min-height: 410px;
            padding: 34px;
            display: flex;
            flex-direction: column;
            justify-content: space-between;
            background-color: #0a1927;
            background-image:
                repeating-linear-gradient(0deg, transparent 0 31px, #17304455 32px),
                repeating-linear-gradient(90deg, transparent 0 31px, #17304455 32px);
            border: 1px solid #1b3a4d;
            border-radius: 8px;
        }
        .login-eyebrow {
            color: #35c9dc;
            font-size: .72rem;
            font-weight: 700;
            letter-spacing: .14em;
        }
        .login-brand h1 {
            color: #e3edf5;
            font-size: 2.7rem;
            line-height: 1.05;
            margin: 22px 0 12px;
        }
        .login-brand-copy { color: #9bb4c4; font-size: 1rem; max-width: 380px; }
        .login-scope { color: #ffc56c; font-size: .76rem; font-weight: 700; }
        .login-form-title { color: #e3edf5; font-size: 1.45rem; font-weight: 700; }
        .login-form-copy { color: #86a4b8; margin-bottom: 1.25rem; }
        div[data-testid="stFormSubmitButton"] button {
            background: #35c9dc;
            color: #07111d;
            border: 0;
            font-weight: 700;
        }
        @media (max-width: 700px) {
            [data-testid="stMainBlockContainer"] { padding: 1rem .75rem; }
            .login-brand { min-height: 270px; padding: 24px; }
            .login-brand h1 { font-size: 2.2rem; }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )
    brand_column, form_column = st.columns([1.1, 0.9], gap="large")
    with brand_column:
        st.markdown(
            """
            <section class="login-brand">
              <div>
                <div class="login-eyebrow">SECURE OPERATIONS ACCESS</div>
                <h1>C.R.I.M.E.<br>Radar</h1>
                <p class="login-brand-copy">
                  Coordinated incident awareness for Tamil Nadu.
                </p>
              </div>
              <div class="login-scope">PRIVATE OPERATOR DASHBOARD · TAMIL NADU ONLY</div>
            </section>
            """,
            unsafe_allow_html=True,
        )
    with form_column:
        st.markdown(
            '<div class="login-form-title">Operator sign in</div>',
            unsafe_allow_html=True,
        )
        st.markdown(
            '<div class="login-form-copy">Use your assigned dashboard credentials.</div>',
            unsafe_allow_html=True,
        )
        login_configured = bool(LOGIN_USERNAME and LOGIN_PASSWORD)
        if not login_configured:
            st.warning("Operator login is not configured for this installation.")
            st.caption(
                "Set CRIME_RADAR_LOGIN_USERNAME and CRIME_RADAR_LOGIN_PASSWORD "
                "in the ignored .env file, then restart the dashboard."
            )

        with st.form("operator-login"):
            username = st.text_input("Operator ID", autocomplete="username")
            password = st.text_input(
                "Password", type="password", autocomplete="current-password"
            )
            submitted = st.form_submit_button(
                "Sign in",
                use_container_width=True,
                disabled=not login_configured,
            )

        if submitted:
            username_matches = hmac.compare_digest(username, LOGIN_USERNAME)
            password_matches = hmac.compare_digest(password, LOGIN_PASSWORD)
            if username_matches and password_matches:
                st.session_state["authenticated"] = True
                st.rerun()
            st.error("Credentials not recognized.")


if not st.session_state.get("authenticated", False):
    render_login_page()
    st.stop()


def haversine(lon1, lat1, lon2, lat2):
    lon1, lat1, lon2, lat2 = map(radians, [lon1, lat1, lon2, lat2])
    dlon, dlat = lon2 - lon1, lat2 - lat1
    a = sin(dlat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(dlon / 2) ** 2
    return 6371 * 2 * asin(sqrt(a))


def nearest_training_station(latitude, longitude, stations):
    if not stations:
        return None, None
    station = min(
        stations,
        key=lambda item: haversine(
            item["longitude"], item["latitude"], longitude, latitude
        ),
    )
    distance_km = haversine(
        station["longitude"], station["latitude"], longitude, latitude
    )
    return station, distance_km


def nearest_training_stations(
    latitude,
    longitude,
    stations,
    max_count=5,
    exclude_station_id=None,
    max_distance_km=None,
):
    if not stations:
        return []
    sorted_stations = sorted(
        stations,
        key=lambda item: haversine(
            item["longitude"], item["latitude"], longitude, latitude
        ),
    )
    results = []
    for station in sorted_stations:
        if station["station_id"] == exclude_station_id:
            continue
        distance_km = haversine(
            station["longitude"], station["latitude"], longitude, latitude
        )
        if max_distance_km is not None and distance_km > max_distance_km:
            break
        results.append((station, distance_km))
        if len(results) >= max_count:
            break
    return results


def focus_incident_on_map(event_id):
    st.session_state["map_focus_event_id"] = str(event_id)


def toggle_incident_map_focus(event_id):
    event_id = str(event_id)
    if st.session_state.get("map_focus_event_id") == event_id:
        st.session_state.pop("map_focus_event_id", None)
        return
    st.session_state["map_focus_event_id"] = event_id


def escape_markdown(value):
    escaped = html.escape(str(value))
    return re.sub(r"([\\`*_{}\[\]()#+\-.!|>])", r"\\\1", escaped)


def record_incident_station_alert(
    incident_id,
    incident_type,
    address,
    latitude,
    longitude,
    station_name,
    distance_km,
):
    incident_queue = st.session_state.setdefault("incident_action_queue", [])
    previous_incidents = st.session_state.setdefault(
        "previous_action_incidents", []
    )
    if (
        incident_id not in incident_queue
        and not any(
            str(item["event_id"]) == str(incident_id)
            for item in previous_incidents
        )
    ):
        return

    st.session_state["last_auto_case_rotation_at"] = time.monotonic()
    sent_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    alert = {
        "sent_at": sent_at,
        "station_name": station_name,
        "incident_id": incident_id,
        "incident_type": incident_type,
        "distance_km": distance_km,
        "address": address,
        "latitude": latitude,
        "longitude": longitude,
    }
    alert_message = (
        "SIMULATED DISPATCH NOTICE — NOT SENT\n"
        f"Case reference: {incident_id}\n"
        f"Incident type: {incident_type}\n"
        f"Assigned station: {station_name} ({distance_km:.2f} km)\n"
        f"Location: {address}\n"
        f"Coordinates: {latitude:.5f}, {longitude:.5f}\n"
        f"Logged: {sent_at}"
    )
    outbox = st.session_state.setdefault("station_alert_outbox", [])
    outbox.append(
        {
            **alert,
            "distance_km": f"{distance_km:.2f}",
            "message": alert_message,
            "status": "SIMULATED — NOT SENT",
        }
    )
    del outbox[:-50]
    if incident_id in incident_queue:
        incident_queue.remove(incident_id)
    previous_incidents[:] = [
        item
        for item in previous_incidents
        if str(item["event_id"]) != str(incident_id)
    ]
    if incident_queue:
        next_incident_id = str(incident_queue[0])
        st.session_state.setdefault("released_action_incident_ids", set()).add(
            next_incident_id
        )
    st.session_state["station_alert_confirmation"] = alert


def is_training_status(status):
    return str(status).strip().upper().startswith(("SIMULATED DEMO", "TRAINING EXERCISE"))


def display_incident_status(status):
    return "OPEN" if is_training_status(status) else str(status)


def display_incident_type(incident_type, is_training):
    value = str(incident_type)
    if is_training and value.strip().upper() == "SIMULATED DEMO EVENT":
        return "INCIDENT"
    return value


def display_incident_address(address, is_training):
    value = str(address)
    if is_training:
        for suffix in (" (simulated location)", " · SYNTHETIC DEMO"):
            value = value.replace(suffix, "")
    return value


def display_event_id(event_id, is_training):
    value = str(event_id)
    if is_training and value.upper().startswith(("SIM-", "DEMO-", "TRAIN-")):
        return f"TN-{value.rsplit('-', 1)[-1]}"
    return value


def display_incident_time(value):
    timestamp = pd.to_datetime(value, errors="coerce", utc=True)
    if pd.isna(timestamp):
        return "Time unavailable"
    local_time = timestamp.to_pydatetime().astimezone(
        timezone(timedelta(hours=5, minutes=30))
    )
    return local_time.strftime("%d %b %Y, %I:%M %p IST")


def render_crime_risk_zones():
    st.markdown(
        '<p class="radar-analytics-heading">REPORTED CRIME RISK</p>'
        '<h1 class="radar-page-heading radar-risk-page-title">Crime risk zones</h1>'
        '<p class="radar-page-copy">Existing reports grouped by area. '
        'Risk levels are relative to the observed report counts, not predictions.</p>',
        unsafe_allow_html=True,
    )

    try:
        incidents_data, _, _, _ = asyncio.run(load_dashboard_data())
    except (requests.RequestException, ValueError, KeyError) as exc:
        st.error(f"Crime report data is unavailable: {exc}")
        return

    incidents_df = pd.DataFrame(incidents_data)
    if incidents_df.empty or "address" not in incidents_df:
        st.info("No existing crime records are currently available.")
        return

    area_names = (
        incidents_df["address"]
        .astype("string")
        .dropna()
        .str.split(",", n=1)
        .str[0]
        .str.strip()
    )
    area_names = area_names.loc[area_names.ne("") & area_names.notna()]
    area_counts = area_names.value_counts().sort_values(ascending=False, kind="stable")
    if area_counts.empty:
        st.info("Existing crime records do not include usable area names.")
        return

    lower_threshold = area_counts.quantile(1 / 3)
    upper_threshold = area_counts.quantile(2 / 3)
    st.caption(
        "Count-based thresholds from the observed areas: Lower ≤ "
        f"{lower_threshold:g} reports; Moderate > {lower_threshold:g} and ≤ "
        f"{upper_threshold:g}; Higher > {upper_threshold:g} reports."
    )

    categories = (
        ("Lower reported crime", "lower"),
        ("Moderate reported crime", "moderate"),
        ("Higher reported crime", "higher"),
    )
    category_columns = st.columns(3, gap="medium")
    for column, (label, level) in zip(category_columns, categories):
        with column:
            area_rows = []
            for area, count in area_counts.items():
                if (
                    (level == "lower" and count <= lower_threshold)
                    or (
                        level == "moderate"
                        and lower_threshold < count <= upper_threshold
                    )
                    or (level == "higher" and count > upper_threshold)
                ):
                    area_rows.append(
                        '<div class="radar-risk-area">'
                        f'<strong>{html.escape(str(area))}</strong>'
                        f'<span>{int(count)} reports</span></div>'
                    )
            if not area_rows:
                area_rows.append(
                    '<p class="radar-risk-empty">No areas fall in this count range.</p>'
                )
            st.markdown(
                f'<section class="radar-risk-card {level}">'
                f'<h3>{label}</h3>{"".join(area_rows)}</section>',
                unsafe_allow_html=True,
            )


def render_complaint_tracking():
    st.markdown(
        '<p class="radar-analytics-heading">COMPLAINT TRACKING</p>'
        '<h1 class="radar-page-heading radar-complaint-page-title">Track Your Complaint</h1>'
        '<p class="radar-page-copy">Browse existing simulated incident records '
        'and their demonstration complaint statuses.</p>',
        unsafe_allow_html=True,
    )
    st.info(
        "DEMO DATA ONLY — statuses and action messages are examples. "
        "They are not saved and do not represent verified reports or police action."
    )

    records = st.session_state.get("dashboard_incidents_for_tracking", [])
    statuses = (
        "Submitted",
        "Under Review",
        "Investigation in Progress",
        "Action Taken",
        "Resolved",
    )
    actions = {
        "Submitted": "Complaint registered successfully.",
        "Under Review": "Complaint is being reviewed.",
        "Investigation in Progress": "Investigation is ongoing (demo status only).",
        "Action Taken": "A demo action update has been recorded.",
        "Resolved": "Complaint marked as resolved (demo status only).",
    }
    badge_colors = {
        "Submitted": "#4c9dff",
        "Under Review": "#f0a33a",
        "Investigation in Progress": "#b58cff",
        "Action Taken": "#48c774",
        "Resolved": "#35c9c1",
    }

    complaints = []
    for record in records:
        if not is_training_status(record.get("status", "")):
            continue
        complaint_id = str(record.get("event_id") or "").strip()
        if not complaint_id:
            continue
        status_index = int.from_bytes(
            hashlib.sha256(complaint_id.encode("utf-8")).digest()[:4],
            "big",
        ) % len(statuses)
        status = statuses[status_index]
        complaints.append(
            {
                "reference": str(record.get("id") or complaint_id),
                "complaint_id": complaint_id,
                "title": str(record.get("incident_type") or "Demo incident"),
                "date": record.get("timestamp"),
                "location": str(record.get("address") or "Not available"),
                "status": status,
                "action": actions[status],
                "details": str(record.get("report_details") or ""),
            }
        )

    if not complaints:
        st.info(
            "No existing dummy complaint records are available. Visit Live "
            "Operations first to load the dashboard's existing incident records."
        )
        return

    search = st.text_input(
        "Search by Complaint ID or title",
        key="track-complaints-search",
        placeholder="Enter an ID or complaint title",
    ).strip().casefold()
    status_filter = st.selectbox(
        "Filter by status",
        ("All statuses", *statuses),
        key="track-complaints-status-filter",
    )
    filtered = [
        complaint for complaint in complaints
        if (
            not search
            or search in complaint["complaint_id"].casefold()
            or search in complaint["title"].casefold()
        )
        and (
            status_filter == "All statuses"
            or complaint["status"] == status_filter
        )
    ]
    st.caption(f"Showing {len(filtered)} of {len(complaints)} existing demo records.")
    if not filtered:
        st.info("No complaints match the current search and status filter.")
        return

    table = pd.DataFrame(
        [
            {
                "Incident Reference": complaint["reference"],
                "Incident Type": complaint["title"],
                "Recorded At": display_incident_time(complaint["date"]),
                "Complaint ID": complaint["complaint_id"],
                "Complaint Status": complaint["status"],
            }
            for complaint in filtered
        ]
    )
    st.dataframe(table, hide_index=True, use_container_width=True)

    labels = {
        item["complaint_id"]: f'{item["complaint_id"]} · {item["status"]}'
        for item in filtered
    }
    selected_id = st.selectbox(
        "Select a complaint to view details",
        [item["complaint_id"] for item in filtered],
        format_func=labels.get,
        key="track-complaints-selected",
    )
    selected = next(
        item for item in filtered if item["complaint_id"] == selected_id
    )
    st.markdown(
        f'<div style="padding:18px;margin:12px 0;background:#0a1927;'
        f'border:1px solid #1b3a4d;border-radius:8px">'
        f'<div style="display:flex;align-items:center;gap:12px;flex-wrap:wrap">'
        f'<h3 style="margin:0;color:#e3edf5">{html.escape(selected["title"])}</h3>'
        f'<span style="padding:5px 11px;border-radius:999px;color:#07111d;'
        f'background:{badge_colors[selected["status"]]};font-weight:700">'
        f'{html.escape(selected["status"])} · DEMO</span></div></div>',
        unsafe_allow_html=True,
    )
    detail_columns = st.columns(2)
    detail_columns[0].markdown(
        f'**Complaint ID**  \n{html.escape(selected["complaint_id"])}'
    )
    detail_columns[1].markdown(
        f'**Complaint date**  \n'
        f'{html.escape(display_incident_time(selected["date"]))}'
    )
    detail_columns[0].markdown(
        f'**Location**  \n{html.escape(selected["location"])}'
    )
    detail_columns[1].markdown(
        f'**Action taken · DEMO**  \n{html.escape(selected["action"])}'
    )
    if selected["details"]:
        st.markdown(f'**Available details**  \n{html.escape(selected["details"])}')

    st.markdown("#### Complaint progress · demonstration")
    current_index = statuses.index(selected["status"])
    for index, status in enumerate(statuses):
        marker = "✓" if index < current_index else "●" if index == current_index else "○"
        label = (
            "Demo step" if index < current_index
            else "Current demo status" if index == current_index
            else "Next example step"
        )
        st.markdown(
            f'<div style="display:flex;align-items:center;gap:10px;'
            f'min-height:36px;padding-left:4px;color:#d7e4ef">'
            f'<span style="color:{badge_colors[status]};font-size:1.15rem">'
            f'{marker}</span><strong>{html.escape(status)}</strong>'
            f'<span style="color:#8faabd;font-size:.82rem">{label}</span></div>',
            unsafe_allow_html=True,
        )


def incident_hud_html(incident, extra_html="", is_active=False):
    status = str(incident.get("status", "UNKNOWN"))
    is_demo = bool(incident.get("is_demo", is_training_status(status)))
    incident_type = html.escape(
        display_incident_type(incident.get("incident_type", "INCIDENT"), is_demo)
    )
    address = html.escape(
        display_incident_address(incident.get("address", "Location unavailable"), is_demo)
    )
    event_id = html.escape(
        display_event_id(incident.get("event_id", "Unknown"), is_demo)
    )
    priority = html.escape(str(incident.get("priority", "UNKNOWN")).upper())
    status = html.escape(display_incident_status(status))
    reported = html.escape(display_incident_time(incident.get("timestamp")))
    latitude = float(incident.get("latitude", 0))
    longitude = float(incident.get("longitude", 0))
    is_report = bool(incident.get("is_report", False))
    report_details = incident.get("report_details")
    if pd.isna(report_details):
        report_details = ""
    report_details = str(report_details or "").strip()
    report_html = (
        '<div class="incident-hud-report"><strong>UNVERIFIED USER REPORT</strong>'
        + (
            f'<br>{html.escape(report_details)}'
            if report_details
            else ""
        )
        + "</div>"
        if is_report
        else ""
    )
    extra_block = (
        f'<div class="incident-hud-extra">{extra_html}</div>' if extra_html else ""
    )
    return (
        '<div class="incident-hud-content">'
        f'<div class="incident-hud-kicker">'
        f'{"ACTIVE INCIDENT" if is_active else "INCIDENT"}</div>'
        f'<div class="incident-hud-title">{incident_type}</div>'
        '<div class="incident-hud-grid">'
        f'<div class="incident-hud-field incident-hud-field-wide">'
        f'<span class="incident-hud-label">Area</span>'
        f'<span class="incident-hud-value">{address}</span></div>'
        f'<div class="incident-hud-field"><span class="incident-hud-label">'
        f'Reported</span><span class="incident-hud-value">{reported}</span></div>'
        f'<div class="incident-hud-field"><span class="incident-hud-label">'
        f'Incident ID</span><span class="incident-hud-value">{event_id}</span></div>'
        f'<div class="incident-hud-field incident-hud-field-wide">'
        f'<span class="incident-hud-label">Position</span>'
        f'<span class="incident-hud-value">{latitude:.5f}, {longitude:.5f}</span></div>'
        '</div>'
        f'<div class="incident-hud-state"><span>{priority}</span>'
        f'<span>{status}</span></div>'
        f'{report_html}{extra_block}</div>'
    )


def training_map_sync_html(selection):
    selection_payload = json.dumps(
        selection, separators=(",", ":"), ensure_ascii=True
    )
    return (
        "<script>window.frameElement.style.display='none';"
        "window.parent.sessionStorage.setItem("
        "'crime-radar-map-selection', "
        f"{json.dumps(selection_payload)}"
        ");window.parent.document.dispatchEvent("
        "new Event('crime-radar-map-update'));"
        "</script>"
    )


def display_patrol_status(status):
    return "AVAILABLE" if is_training_status(status) else str(status)


API_URL = os.getenv("CRIME_RADAR_API_URL", "http://127.0.0.1:8000").rstrip("/")
CASE_ROTATION_SECONDS = 5


def get_json(path, params=None):
    response = requests.get(f"{API_URL}{path}", params=params, timeout=5)
    response.raise_for_status()
    return response.json()


@st.cache_data(ttl=60, max_entries=16, show_spinner=False)
def load_crime_trends(days, include_demo):
    return get_json(
        "/api/v1/analytics/trends",
        params={"days": days, "include_demo": include_demo},
    )


ROUTING_SERVICE_URL = os.getenv(
    "CRIME_RADAR_ROUTING_URL", "https://router.project-osrm.org"
).rstrip("/")


@st.cache_data(ttl=300, max_entries=128, show_spinner=False)
def get_road_route(source_latitude, source_longitude, destination_latitude, destination_longitude):
    response = requests.get(
        f"{ROUTING_SERVICE_URL}/route/v1/driving/"
        f"{source_longitude},{source_latitude};"
        f"{destination_longitude},{destination_latitude}",
        params={"overview": "false", "steps": "false"},
        headers={"User-Agent": "C.R.I.M.E.-Radar-prototype"},
        timeout=10,
    )
    response.raise_for_status()
    payload = response.json()
    routes = payload.get("routes", [])
    if payload.get("code") != "Ok" or not routes:
        raise ValueError("The routing service did not return a road route.")

    route = routes[0]
    return {
        "distance_km": route["distance"] / 1000,
        "duration_minutes": route["duration"] / 60,
    }


async def load_dashboard_data():
    incidents = await asyncio.to_thread(get_json, "/api/v1/active-incidents")
    units, sources, stations = await asyncio.gather(
        asyncio.to_thread(get_json, "/api/v1/patrol-units"),
        asyncio.to_thread(get_json, "/api/v1/sources"),
        asyncio.to_thread(get_json, "/api/v1/police-stations"),
    )
    return incidents, units, sources[0], stations


st.markdown(
    """
    <style>
    :root { color-scheme: dark; }
    .stApp { background: #07111d; color: #d7e4ef; }
    [data-testid="stMainBlockContainer"] { padding: .7rem 1rem 1rem; max-width: 100%; }
    [data-testid="stHeader"] { background: rgba(7, 17, 29, .94); }
    [data-testid="stStatusWidget"] { visibility: hidden; }
    [data-testid="stSidebar"] { background: #091522; border-right: 1px solid #193348; }
    [data-testid="stVerticalBlock"] { gap: .55rem; }
    [data-testid="stMetric"] { background: #0b1b2a; border: 1px solid #1b3a4d;
        border-radius: 8px; padding: 12px 14px; }
    .radar-kicker { color: #6e91a8; font-size: .75rem; letter-spacing: .16em;
        font-weight: 700; text-transform: uppercase; }
    .radar-title { color: #e3edf5; font-size: 1.4rem; font-weight: 750;
        letter-spacing: .025em; margin: 0; }
    .radar-source-note { color: #86a4b8; font-size: .72rem; margin: .25rem 0 0; }
    .radar-toolbar { background: #0a1927; border: 1px solid #1b3a4d;
        border-radius: 6px; padding: 8px 11px; color: #89a9bd; font-size: .76rem; }
    .radar-live-alert { background: #142736; border: 1px solid #1d5267;
        border-left: 3px solid #22bad1; color: #a6dcec; border-radius: 5px;
        padding: 8px 10px; font-size: .8rem; font-weight: 650; }
    .radar-spike-grid {
        display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
        gap: 10px; margin: 10px 0 16px;
    }
    .radar-spike-card {
        min-width: 0; padding: 12px 14px;
        background: linear-gradient(145deg, #102438, #0a1725);
        border: 1px solid #8b6734; border-left: 3px solid #ffbf69;
        border-radius: 8px;
    }
    .radar-spike-card.elevated {
        border-color: #286579; border-left-color: #35c9dc;
    }
    .radar-spike-top {
        display: flex; align-items: center; justify-content: space-between;
        gap: 12px;
    }
    .radar-spike-date { color: #dcebf4; font-size: .82rem; font-weight: 700; }
    .radar-spike-severity {
        flex: 0 0 auto; padding: 3px 7px; border: 1px solid #8b6734;
        border-radius: 999px; color: #ffd28a; font-size: .65rem;
        font-weight: 750; text-transform: uppercase;
    }
    .radar-spike-card.elevated .radar-spike-severity {
        border-color: #286579; color: #7de5f2;
    }
    .radar-spike-count {
        margin-top: 8px; color: #f1f7fb; font-size: 1.2rem; font-weight: 800;
    }
    .radar-spike-detail {
        margin-top: 3px; color: #91aabd; font-size: .72rem; line-height: 1.45;
    }
    .radar-no-spikes {
        margin: 10px 0 16px; padding: 12px 14px;
        background: #0c2030; border: 1px solid #23465b;
        border-radius: 8px; color: #9fb8c9; font-size: .82rem;
    }
    .radar-no-spikes strong { color: #cfe2ee; }
    div[data-testid="stToast"] {
        background: linear-gradient(145deg, #102b40, #0a1927 85%);
        border: 1px solid #2785a5; border-left: 3px solid #35c9dc;
        border-radius: 8px;
        box-shadow: inset 0 1px 0 rgba(117, 226, 255, .14),
            0 0 20px rgba(23, 166, 213, .16);
    }
    div[data-testid="stToast"] [data-testid="stMarkdownContainer"] {
        color: #dff7ff; font-size: .82rem; line-height: 1.45;
    }
    div[data-testid="stToast"] [data-testid="stMarkdownContainer"] p {
        margin: 0;
    }
    .radar-no-feed { color: #ffc56c; font-size: .75rem; font-weight: 700;
        text-align: right; border: 1px solid #594729; background: #241e15;
        border-radius: 5px; padding: 6px 9px; }
    .radar-panel { background: #0a1927; border: 1px solid #1b3a4d;
        border-radius: 8px; padding: 14px; margin-bottom: 12px; }
    .radar-panel h3 { color: #aec6d6; font-size: .9rem; letter-spacing: .06em;
        text-transform: uppercase; margin: 0 0 10px; }
    .radar-alert { background: #35151c; color: #ff8991; border: 1px solid #852b36;
        border-radius: 6px; padding: 9px 11px; font-weight: 700; }
    .radar-zone { background: #0d2232; border-left: 3px solid #22bad1;
        border-radius: 4px; padding: 9px 10px; margin: 7px 0; }
    .radar-zone-critical { border-left-color: #ff4559; }
    .radar-zone small { color: #86a4b8; }
    .radar-cluster-card { background: #0b1b2a; border: 1px solid #1b3a4d;
        border-left: 3px solid #22bad1; border-radius: 4px; padding: 8px 9px;
        margin: 6px 0; color: #d7e4ef; font-size: .78rem; }
    .radar-cluster-card small { color: #86a4b8; }
    .radar-cluster-count { float: right; color: #45c6d8; font-size: 1rem;
        font-weight: 800; }
    div[data-testid="stVerticalBlockBorderWrapper"]:has(.incident-hud-content),
    div[data-testid="stVerticalBlockBorderWrapper"]:has(.radar-trend-page) {
        background: linear-gradient(145deg, #0c2235, #081523 75%);
        border: 1px solid #287f96; border-radius: 6px; padding: 10px 12px;
        box-shadow: inset 0 1px 0 rgba(89, 214, 232, .12),
            0 0 16px rgba(20, 190, 220, .1);
    }
    .radar-risk-card { background: #0a1927; border: 1px solid #1b3a4d;
        border-left: 3px solid #1b3a4d; border-radius: 8px; padding: 14px;
        min-height: 100%; }
    .radar-risk-card h3 { color: #aec6d6; font-size: .9rem;
        letter-spacing: .04em; margin: 0 0 12px; }
    .radar-risk-card.lower { border-left-color: #83c995; }
    .radar-risk-card.lower h3 { color: #83c995; }
    .radar-risk-card.moderate { border-left-color: #f0a33a; }
    .radar-risk-card.moderate h3 { color: #f0a33a; }
    .radar-risk-card.higher { border-left-color: #ff4559; }
    .radar-risk-card.higher h3 { color: #ff4559; }
    .radar-risk-area { display: flex; justify-content: space-between;
        gap: 10px; padding: 8px 0; border-top: 1px solid #1b3a4d;
        color: #d7e4ef; font-size: .82rem; }
    .radar-risk-area strong { overflow-wrap: anywhere; }
    .radar-risk-area span { color: #86a4b8; white-space: nowrap; }
    .radar-risk-empty { color: #86a4b8; font-size: .82rem; }
    div[data-testid="stVerticalBlockBorderWrapper"]:has(.radar-risk-page-title) {
        background: linear-gradient(145deg, #0c2235, #091522 75%);
        border: 1px solid #24566a; border-top: 3px solid #45c6d8;
        border-radius: 12px; padding: 18px 20px;
        box-shadow: 0 8px 24px rgba(69, 198, 216, .08);
    }
    div[data-testid="stVerticalBlockBorderWrapper"]:has(.radar-complaint-page-title) {
        background: linear-gradient(145deg, #0c2235, #091522 75%);
        border: 1px solid #24566a; border-top: 3px solid #45c6d8;
        border-radius: 12px; padding: 18px 20px;
        box-shadow: 0 8px 24px rgba(69, 198, 216, .08);
    }
    .incident-hud-kicker { color: #59d6e8; font-size: .65rem; font-weight: 750;
        letter-spacing: .14em; text-transform: uppercase; }
    .incident-hud-title { color: #effaff; font-size: .98rem; font-weight: 750;
        line-height: 1.25; margin: 4px 0 9px; overflow-wrap: anywhere; }
    .incident-hud-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 7px; }
    .incident-hud-field { background: #0b2437; border-left: 2px solid #197b91;
        min-width: 0; padding: 6px 8px; }
    .incident-hud-field-wide { grid-column: 1 / -1; }
    .incident-hud-label { color: #70aabc; display: block; font-size: .58rem;
        font-weight: 750; letter-spacing: .1em; text-transform: uppercase; }
    .incident-hud-value { color: #e0f1f5; display: block; font-size: .76rem;
        line-height: 1.4; margin-top: 3px; overflow-wrap: anywhere; }
    .incident-hud-state { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 8px; }
    .incident-hud-state span { background: #102d40; border: 1px solid #22677c;
        border-radius: 3px; color: #89e5ef; font-size: .59rem; font-weight: 750;
        letter-spacing: .07em; padding: 3px 6px; }
    .incident-hud-report, .incident-hud-extra { border-top: 1px solid #174054;
        color: #a8cbd5; font-size: .72rem; line-height: 1.5; margin-top: 9px;
        padding-top: 8px; overflow-wrap: anywhere; }
    div[data-testid="stVerticalBlockBorderWrapper"]:has(.incident-hud-content)
        [data-testid="stButton"] button {
        background: #0c2a3e; border: 1px solid #287f96; color: #b9edf3;
    }
    div[data-testid="stVerticalBlockBorderWrapper"]:has(.incident-hud-content)
        [data-testid="stButton"] button:hover {
        border-color: #59d6e8; color: #effaff;
        box-shadow: 0 0 12px rgba(20, 190, 220, .2);
    }
    .radar-status { color: #62d6a5; font-size: .8rem; font-weight: 700; }
    div[data-testid="stDataFrame"] { border: 1px solid #1b3a4d; border-radius: 8px; }
    div[data-testid="stMultiSelect"] [data-baseweb="tag"] {
        background: linear-gradient(135deg, #124458, #126878);
        border: 1px solid #35c9dc;
        border-radius: 999px;
        box-shadow: 0 0 10px rgba(53, 201, 220, .16);
        animation: station-chip-in .2s ease-out;
        transition: box-shadow .18s ease, transform .18s ease;
    }
    div[data-testid="stMultiSelect"] [data-baseweb="tag"]:hover {
        box-shadow: 0 0 15px rgba(53, 201, 220, .38);
        transform: translateY(-1px);
    }
    div[data-testid="stMultiSelect"]:focus-within [data-baseweb="select"] > div {
        border-color: #35c9dc;
        box-shadow: 0 0 0 1px #35c9dc, 0 0 14px rgba(53, 201, 220, .2);
    }
    @keyframes station-chip-in {
        from { opacity: .45; transform: scale(.92); }
        to { opacity: 1; transform: scale(1); }
    }
    iframe[title="st.iframe"][height="700"] {
        opacity: 1 !important;
        filter: none !important;
        transition: none !important;
        border: 1px solid #1b3a4d;
        border-radius: 8px;
        box-shadow: 0 0 22px rgba(8, 184, 211, .08);
    }
    div[data-testid="element-container"]:has(> iframe[title="st.iframe"][height="700"]) {
        opacity: 1 !important;
        transition: none !important;
    }
    div[data-testid="stHorizontalBlock"]:has(iframe[title="st.iframe"][height="700"])
        > div[data-testid="column"]:first-child {
        position: relative;
        min-width: 0;
        padding: 10px 12px;
        background: #091522;
        border: 1px solid #1b3a4d;
        border-radius: 6px;
        box-shadow: inset 0 1px 0 rgba(104, 202, 223, .08);
    }
    :root {
        --radar-bg: #07111d;
        --radar-panel: #0c1b2b;
        --radar-border: #1e3a50;
        --radar-muted: #91a8bb;
        --radar-accent: #35c9dc;
        --radar-text: #e7f0f7;
    }
    html { scroll-behavior: smooth; }
    body, [data-testid="stAppViewContainer"] {
        color: var(--radar-text);
    }
    [data-testid="stMainBlockContainer"] {
        padding: 1.25rem clamp(1rem, 2.8vw, 2.6rem) 2.5rem;
    }
    [data-testid="stHeader"] {
        background: rgba(7, 17, 29, .78);
        backdrop-filter: blur(16px);
    }
    [data-testid="stVerticalBlock"] { gap: .8rem; }
    [data-testid="stHorizontalBlock"] { gap: 1rem; }
    .radar-command-header {
        position: relative;
        display: flex;
        align-items: center;
        justify-content: space-between;
        gap: 1rem;
        overflow: hidden;
        padding: 1.15rem 1.35rem;
        background:
            radial-gradient(ellipse at 0% 0%, rgba(41, 194, 218, .15), transparent 48%),
            linear-gradient(115deg, #0d2030, #0a1725 68%, #101b32);
        border: 1px solid #244459;
        border-radius: 16px;
        box-shadow: 0 18px 45px rgba(0, 0, 0, .24);
    }
    .radar-brand-lockup { display: flex; align-items: center; gap: 1rem; }
    .radar-brand-mark {
        display: grid;
        place-items: center;
        width: 48px;
        height: 48px;
        flex: 0 0 48px;
        color: #07111d;
        background: linear-gradient(145deg, #6be6f2, #27a9c0);
        border-radius: 14px;
        box-shadow: 0 0 28px rgba(53, 201, 220, .24);
        font-size: 1.25rem;
        font-weight: 900;
    }
    .radar-command-header .radar-title { font-size: clamp(1rem, 2vw, 1.45rem); }
    .radar-command-header .radar-source-note { margin-top: .25rem; }
    .radar-header-meta {
        color: #91a8bb;
        font-size: .72rem;
        font-weight: 700;
        letter-spacing: .09em;
        text-align: right;
        text-transform: uppercase;
    }
    .radar-header-meta strong {
        display: block;
        margin-bottom: .35rem;
        color: #d8e7f1;
    }
    .radar-page-heading {
        margin: .35rem 0 0;
        color: #f0f6fa;
        font-size: clamp(1.3rem, 2.5vw, 2rem);
        font-weight: 780;
        letter-spacing: -.035em;
    }
    .radar-page-copy { margin: 0; color: var(--radar-muted); font-size: .9rem; }
    div[role="radiogroup"] {
        gap: .65rem;
        padding: .4rem;
        background: rgba(11, 27, 42, .84);
        border: 1px solid var(--radar-border);
        border-radius: 12px;
    }
    div[role="radiogroup"] label {
        min-height: 40px;
        padding: .35rem .8rem;
        border: 1px solid transparent;
        border-radius: 9px;
        transition: background .18s ease, border-color .18s ease;
    }
    div[role="radiogroup"] label:has(input:checked) {
        background: linear-gradient(135deg, #12384a, #104356);
        border-color: #27647a;
    }
    [data-testid="stMetric"] {
        min-height: 104px;
        background:
            radial-gradient(ellipse at 100% 0%, rgba(53, 201, 220, .09), transparent 58%),
            linear-gradient(145deg, #102338, #0b1928);
        border: 1px solid #234258;
        border-top: 2px solid #2ab9ce;
        border-radius: 14px;
        padding: 14px 16px;
        box-shadow: 0 12px 28px rgba(0, 0, 0, .17);
    }
    [data-testid="stMetricLabel"] { color: #9ab4c6; font-size: .78rem; }
    [data-testid="stMetricValue"] { color: #f0f7fc; font-size: 1.65rem; }
    [data-testid="stMetricDelta"] { font-size: .76rem; }
    .radar-panel {
        background: linear-gradient(145deg, #102438, #0a1725);
        border: 1px solid #24465b;
        border-radius: 14px;
        padding: 16px;
        box-shadow: 0 14px 34px rgba(0, 0, 0, .16);
    }
    .radar-panel h3 {
        color: #d4e5ef;
        font-size: .86rem;
        letter-spacing: .09em;
    }
    div[data-testid="stVerticalBlockBorderWrapper"]:has(.related-incident-heading) {
        background: linear-gradient(145deg, #102438, #0a1725);
        border: 1px solid #24465b;
        border-left: 3px solid #2ab9ce;
        border-radius: 10px;
        padding: 12px 14px 8px;
        box-shadow: 0 12px 28px rgba(0, 0, 0, .16);
    }
    .related-incident-heading {
        align-items: center;
        display: flex;
        justify-content: space-between;
        gap: 12px;
        margin: 0 0 8px;
    }
    .related-incident-type {
        color: #67d6e5;
        font-size: .9rem;
        font-weight: 750;
        margin: 0;
    }
    .related-incident-count {
        background: #12384a;
        border: 1px solid #27647a;
        border-radius: 999px;
        color: #d7e4ef;
        flex: 0 0 auto;
        font-size: .72rem;
        font-weight: 700;
        padding: 4px 9px;
    }
    .radar-analytics-heading {
        color: #67d6e5;
        font-size: .72rem;
        letter-spacing: .14em;
    }
    .radar-analytics-subtitle { font-size: .9rem; }
    div[data-testid="stButton"] button,
    div[data-testid="stFormSubmitButton"] button {
        min-height: 42px;
        border: 1px solid #2b5268;
        border-radius: 10px;
        transition: border-color .16s ease, transform .16s ease, box-shadow .16s ease;
    }
    div[data-testid="stButton"] button:hover,
    div[data-testid="stFormSubmitButton"] button:hover {
        border-color: #43c7da;
        box-shadow: 0 0 20px rgba(53, 201, 220, .15);
        transform: translateY(-1px);
    }
    div[data-testid="stTextInput"] input,
    div[data-testid="stSelectbox"] [data-baseweb="select"] > div {
        min-height: 42px;
        background: #0b1b2a;
        border-color: #29465a;
        border-radius: 10px;
    }
    div[data-testid="stTextInput"] input:focus,
    div[data-testid="stSelectbox"] [data-baseweb="select"]:focus-within > div {
        border-color: var(--radar-accent);
        box-shadow: 0 0 0 1px var(--radar-accent), 0 0 18px rgba(53, 201, 220, .12);
    }
    div[data-testid="stAlert"] { border-radius: 12px; }
    div[data-testid="stDataFrame"] { overflow: hidden; border-radius: 12px; }
    div[data-testid="stHorizontalBlock"]:has(iframe[title="st.iframe"][height="700"])
        > div[data-testid="column"]:first-child {
        position: sticky !important;
        top: 1rem;
        left: auto;
        bottom: auto;
        width: auto !important;
        height: fit-content;
        max-height: calc(100vh - 2rem);
        overflow-y: auto;
        padding: 12px;
        background: linear-gradient(155deg, #0d2030, #091522);
        border: 1px solid #1e3a50;
        border-radius: 14px;
        box-shadow: 0 14px 34px rgba(0, 0, 0, .2);
    }
    div[data-testid="stHorizontalBlock"]:has(iframe[title="st.iframe"][height="700"])
        > div[data-testid="column"]:first-child::after {
        content: none;
    }
    iframe[title="st.iframe"][height="700"] {
        height: min(780px, 86vh) !important;
        min-height: 620px;
        border: 1px solid #24465b;
        border-radius: 14px;
        box-shadow: 0 18px 42px rgba(0, 0, 0, .2), 0 0 28px rgba(8, 184, 211, .08);
    }
    @media (max-width: 900px) {
        [data-testid="stMainBlockContainer"] { padding: .9rem .85rem 2rem; }
        .radar-command-header { align-items: flex-start; padding: 1rem; }
        .radar-header-meta { font-size: .65rem; }
        div[data-testid="stHorizontalBlock"]:has(iframe[title="st.iframe"][height="700"])
            > div[data-testid="column"]:first-child {
            position: relative !important;
            top: auto;
            max-height: none;
        }
        iframe[title="st.iframe"][height="700"] {
            height: min(760px, 72vh) !important;
            min-height: 460px;
        }
    }
    @media (max-width: 560px) {
        .radar-command-header { flex-direction: column; }
        .radar-header-meta { text-align: left; }
        .radar-brand-mark { width: 40px; height: 40px; flex-basis: 40px; }
        div[role="radiogroup"] { flex-wrap: wrap; }
        div[role="radiogroup"] label { flex: 1 1 100%; }
        [data-testid="stMetric"] { min-height: 88px; padding: 11px 12px; }
    }
    </style>
    """,
    unsafe_allow_html=True,
)


def render_login_page():
    st.markdown(
        '<p class="radar-analytics-heading">SECURE OPERATOR ACCESS</p>'
        '<h1 class="radar-page-heading">Sign in to C.R.I.M.E. Radar</h1>'
        '<p class="radar-page-copy">Private operations dashboard · Tamil Nadu</p>',
        unsafe_allow_html=True,
    )
    brand_column, form_column = st.columns([1.2, 1], gap="large")
    with brand_column:
        st.markdown(
            '<div class="radar-panel"><h3>CRIME HOTSPOT MAPPING</h3>'
            '<p>Coordinated incident awareness for Tamil Nadu.</p>'
            '<small>PRIVATE OPERATOR DASHBOARD · TAMIL NADU ONLY</small></div>',
            unsafe_allow_html=True,
        )
    with form_column:
        with st.container(border=True):
            st.markdown("### Operator sign in")
            configured_username, configured_password = load_login_credentials()
            login_configured = bool(configured_username and configured_password)
            if not login_configured:
                st.warning("Operator sign-in is not configured for this installation.")
                st.caption(
                    "Set CRIME_RADAR_LOGIN_USERNAME and CRIME_RADAR_LOGIN_PASSWORD "
                    "in the ignored .env file, then restart the dashboard."
                )
            with st.form("operator-login"):
                username = st.text_input("Operator ID", autocomplete="username")
                password = st.text_input(
                    "Password", type="password", autocomplete="current-password"
                )
                submitted = st.form_submit_button(
                    "Sign in",
                    use_container_width=True,
                    disabled=not login_configured,
                )
            if submitted:
                sanitized_username = username.strip()
                sanitized_password = password.strip()
                username_matches = hmac.compare_digest(
                    sanitized_username, configured_username
                )
                password_matches = hmac.compare_digest(
                    sanitized_password, configured_password
                )
                if username_matches and password_matches:
                    st.session_state["authenticated"] = True
                    st.rerun()
                st.error("Credentials not recognized.")


if not st.session_state.get("authenticated", False):
    render_login_page()
    st.stop()

header_left, header_right = st.columns([4, 1])
with header_left:
    st.markdown(
        '<div class="radar-command-header"><div class="radar-brand-lockup">'
        '<div class="radar-brand-mark">R</div><div>'
        '<p class="radar-title">CRIME HOTSPOT MAPPING — TAMIL NADU</p>'
        '<p class="radar-source-note">C.R.I.M.E. RADAR · COORDINATED RESPONSE & '
        'INCIDENT MAPPING ENGINE</p></div></div>'
        '<div class="radar-header-meta"><strong>OPERATOR CONSOLE</strong>'
        'TAMIL NADU · PRIVATE ACCESS</div></div>',
        unsafe_allow_html=True,
    )
with header_right:
    if st.button("Sign out", key="operator-sign-out", use_container_width=True):
        st.session_state.pop("authenticated", None)
        st.rerun()
    st.markdown(
        f'<p class="radar-no-feed">● NO LIVE AGENCY FEED<br>'
        f'<span style="font-weight:400">{time.strftime("%H:%M")} LOCAL · TN ONLY</span></p>',
        unsafe_allow_html=True,
    )

st.divider()

dashboard_page = st.radio(
    "Dashboard",
    options=[
        "◉  Live operations",
        "↗  Crime Analysis",
        "▤  Track Complaint",
        "◈  Related crime incidents",
        "◈  Crime risk zones",
    ],
    horizontal=True,
    label_visibility="collapsed",
    key="command-center-page",
)

def render_related_incidents():
    st.markdown(
        '<p class="radar-analytics-heading">CRIME INTELLIGENCE</p>'
        '<h1 class="radar-page-heading">Related crime incidents</h1>'
        '<p class="radar-page-copy">Review incidents of the same crime type and when they were reported.</p>',
        unsafe_allow_html=True,
    )
    st.button("Refresh incident list", key="refresh-related-incidents")

    try:
        incidents = get_json("/api/v1/active-incidents")
    except (requests.RequestException, ValueError, KeyError, TypeError) as exc:
        st.error(f"Incident records unavailable: {exc}")
        return

    if not incidents:
        st.info("No active incident records are available.")
        return

    incidents = [
        incident
        for incident in incidents
        if not is_training_status(incident.get("status", ""))
    ]
    if not incidents:
        st.info("No non-demo incident records are available.")
        return

    incident_df = pd.DataFrame(incidents)
    required_columns = {"event_id", "incident_type", "timestamp"}
    if not required_columns.issubset(incident_df.columns):
        st.error("The incident service returned records without the required incident type, ID, or date fields.")
        return

    incident_df["timestamp"] = pd.to_datetime(incident_df["timestamp"], errors="coerce")
    incident_df = incident_df.dropna(subset=["timestamp"]).copy()
    incident_df["incident_type"] = incident_df["incident_type"].fillna("Unclassified")
    incident_df = incident_df.sort_values("timestamp", ascending=False)

    incident_types = sorted(incident_df["incident_type"].astype(str).unique())
    selected_type = st.selectbox(
        "Crime type",
        ["All types", *incident_types],
        key="related-incidents-crime-type",
    )
    if selected_type != "All types":
        incident_df = incident_df[incident_df["incident_type"].astype(str) == selected_type]

    st.metric("Incidents shown", len(incident_df))
    display_columns = {
        "event_id": "Incident ID",
        "incident_type": "Crime type",
        "timestamp": "Reported date and time",
        "address": "Location",
        "status": "Status",
    }
    for incident_type, related_df in incident_df.groupby("incident_type", sort=True):
        with st.container(border=True):
            st.markdown(
                '<div class="related-incident-heading">'
                f'<h3 class="related-incident-type">{html.escape(str(incident_type))}</h3>'
                f'<span class="related-incident-count">{len(related_df)} incidents</span>'
                '</div>',
                unsafe_allow_html=True,
            )
            display_df = related_df.reindex(columns=display_columns.keys()).rename(
                columns=display_columns
            )
            display_df["Reported date and time"] = display_df[
                "Reported date and time"
            ].dt.strftime("%Y-%m-%d %H:%M")
            st.dataframe(display_df, hide_index=True, use_container_width=True)


def normalize_cluster_type(value):
    text = str(value or "").strip().upper()
    aliases = {
        "ASSAULT": "ASSAULT",
        "ROBBERY": "ROBBERY",
        "THEFT": "THEFT",
        "VEHICLE THEFT": "VEHICLE THEFT",
        "CAR THEFT": "VEHICLE THEFT",
        "AUTO THEFT": "VEHICLE THEFT",
        "BURGLARY": "THEFT",
        "SNATCHING": "THEFT",
        "HARASSMENT": "ASSAULT",
    }
    return aliases.get(text, text or "OTHER")


def haversine_km_between(lat1, lon1, lat2, lon2):
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


def build_live_cluster_payload(incidents, filters):
    if not incidents:
        return {"clusters": [], "demo_mode": False, "message": "No live incidents available.", "total_incidents": 0, "total_clusters": 0}

    radius_km = float(filters.get("radius_km", 5.0))
    time_window_hours = float(filters.get("time_window_hours", 24.0))
    similarity_threshold = float(filters.get("similarity_threshold", 0.55))
    crime_type_filter = filters.get("crime_type")

    normalized_incidents = []
    for record in incidents:
        try:
            lat = float(record.get("latitude"))
            lon = float(record.get("longitude"))
        except (TypeError, ValueError):
            continue
        timestamp_value = pd.to_datetime(record.get("timestamp"), errors="coerce")
        if pd.isna(timestamp_value):
            continue
        incident_type = normalize_cluster_type(record.get("incident_type") or record.get("crime_type") or "OTHER")
        if crime_type_filter and incident_type != crime_type_filter:
            continue
        normalized_incidents.append(
            {
                "event_id": str(record.get("event_id") or record.get("id") or "UNKNOWN"),
                "incident_type": incident_type,
                "status": str(record.get("status") or "ACTIVE_DISPATCH"),
                "priority": str(record.get("priority") or "UNKNOWN"),
                "address": str(record.get("address") or "Location unavailable"),
                "timestamp": timestamp_value.to_pydatetime(),
                "latitude": lat,
                "longitude": lon,
                "report_details": str(record.get("report_details") or ""),
            }
        )

    if len(normalized_incidents) < 2:
        return {"clusters": [], "demo_mode": False, "message": "Not enough valid incident records to cluster.", "total_incidents": len(normalized_incidents), "total_clusters": 0}

    clusters = []
    visited = set()
    for index, incident in enumerate(normalized_incidents):
        if index in visited:
            continue
        cluster_members = [incident]
        visited.add(index)
        for candidate_index in range(index + 1, len(normalized_incidents)):
            if candidate_index in visited:
                continue
            candidate = normalized_incidents[candidate_index]
            distance_km = haversine_km_between(incident["latitude"], incident["longitude"], candidate["latitude"], candidate["longitude"])
            if distance_km > radius_km:
                continue
            hours_delta = abs((incident["timestamp"] - candidate["timestamp"]).total_seconds() / 3600)
            if hours_delta > time_window_hours:
                continue
            same_type = incident["incident_type"] == candidate["incident_type"]
            if not same_type:
                continue
            match_score = 1.0 if same_type else 0.0
            if match_score < similarity_threshold:
                continue
            cluster_members.append(candidate)
            visited.add(candidate_index)
        if len(cluster_members) > 1:
            clusters.append(cluster_members)

    cluster_payload = []
    for cluster_index, group in enumerate(clusters, start=1):
        centroid_lat = sum(item["latitude"] for item in group) / len(group)
        centroid_lon = sum(item["longitude"] for item in group) / len(group)
        sorted_group = sorted(group, key=lambda item: item["timestamp"], reverse=True)
        cluster_id = f"CL-{cluster_index:03d}"
        reasons = []
        for left_index, left in enumerate(sorted_group[:-1]):
            for right in sorted_group[left_index + 1 :]:
                distance_km = haversine_km_between(left["latitude"], left["longitude"], right["latitude"], right["longitude"])
                hours_delta = abs((left["timestamp"] - right["timestamp"]).total_seconds() / 3600)
                if distance_km <= radius_km and hours_delta <= time_window_hours and left["incident_type"] == right["incident_type"]:
                    reasons.append(
                        {
                            "event_ids": [left["event_id"], right["event_id"]],
                            "score": round(min(1.0, max(0.55, 1.0 - (distance_km / max(radius_km, 1.0)) * 0.2 - (hours_delta / max(time_window_hours, 1.0)) * 0.15)), 2),
                            "reasons": [
                                f"Same type: {left['incident_type']}",
                                f"Within {distance_km:.1f} km",
                                f"Reported within {hours_delta:.1f} hours",
                            ],
                        }
                    )
        cluster_payload.append(
            {
                "cluster_id": cluster_id,
                "crime_type": group[0]["incident_type"],
                "incident_count": len(group),
                "review_status": "NEW",
                "area": f"{centroid_lat:.4f}, {centroid_lon:.4f}",
                "centroid_latitude": round(centroid_lat, 5),
                "centroid_longitude": round(centroid_lon, 5),
                "start_date": min(item["timestamp"] for item in sorted_group).isoformat(),
                "end_date": max(item["timestamp"] for item in sorted_group).isoformat(),
                "incident_ids": [item["event_id"] for item in sorted_group],
                "incidents": [
                    {
                        "event_id": item["event_id"],
                        "timestamp": item["timestamp"].isoformat(),
                        "latitude": item["latitude"],
                        "longitude": item["longitude"],
                        "incident_type": item["incident_type"],
                        "status": item["status"],
                        "priority": item["priority"],
                        "address": item["address"],
                        "report_details": item["report_details"],
                    }
                    for item in sorted_group
                ],
                "reasons": reasons[:5],
            }
        )

    return {
        "clusters": cluster_payload,
        "demo_mode": False,
        "message": "Live incident data loaded.",
        "total_incidents": len(normalized_incidents),
        "total_clusters": len(cluster_payload),
    }


def fetch_incident_clusters(filters):
    live_incidents = st.session_state.get("dashboard_incidents_for_tracking", [])
    if not live_incidents:
        try:
            live_incidents = get_json("/api/v1/active-incidents")
            st.session_state["dashboard_incidents_for_tracking"] = live_incidents
        except (requests.RequestException, ValueError, KeyError, TypeError):
            live_incidents = []

    if live_incidents:
        return build_live_cluster_payload(live_incidents, filters), False

    try:
        payload = get_json("/api/v1/incident-clusters", params=filters)
        if isinstance(payload, dict) and payload.get("clusters"):
            return payload, False
        if isinstance(payload, dict):
            return payload, payload.get("demo_mode", False)
    except (requests.RequestException, ValueError, KeyError, TypeError) as exc:
        pass

    return {
        "clusters": [
            {
                "cluster_id": "DEMO-CL-001",
                "crime_type": "THEFT",
                "incident_count": 3,
                "review_status": "NEW",
                "area": "13.0910, 80.2650",
                "centroid_latitude": 13.0910,
                "centroid_longitude": 80.2650,
                "start_date": "2026-10-16T10:55:00",
                "end_date": "2026-10-17T01:15:00",
                "incident_ids": ["DEMO-CASE-100", "DEMO-CASE-101", "DEMO-CASE-102"],
                "incidents": [
                    {"event_id": "DEMO-CASE-100", "timestamp": "2026-10-16T10:55:00", "incident_type": "THEFT", "address": "Mylapore", "status": "ACTIVE_DISPATCH", "priority": "HIGH", "latitude": 13.0910, "longitude": 80.2650, "report_details": "Cash bag reported missing near station exit."},
                    {"event_id": "DEMO-CASE-101", "timestamp": "2026-10-16T12:10:00", "incident_type": "THEFT", "address": "Mylapore", "status": "ACTIVE_DISPATCH", "priority": "HIGH", "latitude": 13.0940, "longitude": 80.2680, "report_details": "Mobile phone snatched by two suspects."},
                    {"event_id": "DEMO-CASE-102", "timestamp": "2026-10-17T01:15:00", "incident_type": "THEFT", "address": "Mylapore", "status": "ACTIVE_DISPATCH", "priority": "HIGH", "latitude": 13.0885, "longitude": 80.2618, "report_details": "Bag stolen from a parked scooter."},
                ],
                "reasons": [{"event_ids": ["DEMO-CASE-100", "DEMO-CASE-101"], "score": 0.82, "reasons": ["Same or related category: THEFT / THEFT", "Within 1.6 km of each other", "Reported within 1.3 hours"]}],
            }
        ],
        "demo_mode": True,
        "message": "Connected incident data unavailable — showing demonstration clusters only.",
        "total_incidents": 3,
        "total_clusters": 1,
    }, True


def render_incident_clustering_dashboard():
    st.markdown(
        '<p class="radar-analytics-heading">CRIME INTELLIGENCE</p>'
        '<h1 class="radar-page-heading">Incident clustering</h1>'
        '<p class="radar-page-copy">Group nearby related incidents by location, crime type, and reporting window to surface possible investigative leads.</p>',
        unsafe_allow_html=True,
    )

    with st.container(border=True):
        cluster_filters = {}
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            cluster_filters["crime_type"] = st.selectbox(
                "Crime type",
                ["All types", "THEFT", "ROBBERY", "ASSAULT", "VEHICLE THEFT"],
                index=0,
            )
        with col2:
            cluster_filters["radius_km"] = st.slider(
                "Radius (km)",
                min_value=1.0,
                max_value=20.0,
                value=5.0,
                step=0.5,
            )
        with col3:
            cluster_filters["time_window_hours"] = st.slider(
                "Time window (hrs)",
                min_value=2,
                max_value=72,
                value=24,
                step=2,
            )
        with col4:
            cluster_filters["similarity_threshold"] = st.slider(
                "Similarity",
                min_value=0.1,
                max_value=1.0,
                value=0.55,
                step=0.05,
            )

        if st.button("Refresh cluster review list", use_container_width=True, type="primary"):
            st.rerun()

    if cluster_filters["crime_type"] != "All types":
        cluster_filters["crime_type"] = cluster_filters["crime_type"]
    else:
        cluster_filters["crime_type"] = None
    cluster_filters["review_status"] = None

    with st.spinner("Scanning incident records and forming clusters..."):
        response, demo_mode = fetch_incident_clusters(cluster_filters)

    if response.get("demo_mode"):
        st.caption(response.get("message", "No live incident records were available; sample clusters are shown for demonstration."))

    clusters = response.get("clusters", [])
    total_incidents = response.get("total_incidents", sum(cluster.get("incident_count", 0) for cluster in clusters))
    awaiting_review = sum(1 for cluster in clusters if cluster.get("review_status") in {"NEW", "UNDER_REVIEW"})
    recently_updated = max(0, len(clusters))

    overview = st.columns(4)
    overview[0].metric("Total incidents", total_incidents)
    overview[1].metric("Detected clusters", len(clusters))
    overview[2].metric("Awaiting review", awaiting_review)
    overview[3].metric("Recently updated", recently_updated)

    if not clusters:
        st.info("No clusters matched the current filters. Adjust the crime type, radius, or time window and retry.")
        return

    selected_cluster_id = st.selectbox(
        "Cluster focus",
        [cluster["cluster_id"] for cluster in clusters],
        format_func=lambda cluster_id: f"{cluster_id} · {next((item['crime_type'] for item in clusters if item['cluster_id'] == cluster_id), 'Cluster')}",
        key="incident-cluster-select",
    )
    selected_cluster = next((cluster for cluster in clusters if cluster["cluster_id"] == selected_cluster_id), clusters[0])

    map_center = [selected_cluster.get("centroid_latitude", 13.09), selected_cluster.get("centroid_longitude", 80.27)]
    m = folium.Map(location=map_center, zoom_start=10, tiles="Cartodb dark_matter")
    status_colors = {
        "NEW": "#52c7ff",
        "UNDER_REVIEW": "#ffb347",
        "REVIEWED": "#49d38d",
        "NEEDS_FURTHER_INVESTIGATION": "#ff6272",
    }
    for cluster in clusters:
        fill_color = status_colors.get(cluster.get("review_status", "NEW"), "#52c7ff")
        folium.CircleMarker(
            location=[cluster.get("centroid_latitude", map_center[0]), cluster.get("centroid_longitude", map_center[1])],
            radius=max(12, min(28, cluster.get("incident_count", 1) * 6)),
            popup=f"{cluster['cluster_id']} · {cluster['crime_type']} ({cluster['incident_count']} incidents)",
            color=fill_color,
            fill=True,
            fill_opacity=0.22,
            weight=2,
        ).add_to(m)
        for incident in cluster.get("incidents", []):
            folium.Marker(
                [incident.get("latitude", map_center[0]), incident.get("longitude", map_center[1])],
                popup=f"{incident.get('event_id')} · {incident.get('incident_type')} · {incident.get('status')}",
                icon=folium.Icon(color="lightred", icon="info-sign"),
            ).add_to(m)

    st.markdown("#### Cluster map")
    components.html(m.get_root().render(), height=480, scrolling=False)

    table_rows = []
    for cluster in clusters:
        table_rows.append(
            {
                "Cluster ID": cluster["cluster_id"],
                "Crime type": cluster["crime_type"],
                "Incidents": cluster["incident_count"],
                "Area": cluster.get("area", "Unknown"),
                "Date range": f"{cluster.get('start_date','-')[:10]} to {cluster.get('end_date','-')[:10]}",
                "Status": cluster.get("review_status", "NEW"),
            }
        )
    table_df = pd.DataFrame(table_rows)
    st.dataframe(table_df, hide_index=True, use_container_width=True)

    detail_col, review_col = st.columns([1.8, 1.2])
    with detail_col:
        st.markdown("#### Cluster review")
        st.markdown(f"**Cluster:** {selected_cluster['cluster_id']}")
        st.markdown(f"**Primary type:** {selected_cluster['crime_type']}")
        st.markdown(f"**Reports in cluster:** {selected_cluster['incident_count']}")
        st.markdown(f"**Area:** {selected_cluster.get('area', 'Unknown')}")
        st.markdown(f"**Date window:** {selected_cluster.get('start_date', '-')[:10]} to {selected_cluster.get('end_date', '-')[:10]}")
        st.markdown("**Why these reports were grouped**")
        for item in selected_cluster.get("reasons", [])[:5]:
            st.markdown(f"- {item['score']:.2f} match · {', '.join(item.get('reasons', []))}")
        st.markdown("**Reports in this cluster**")
        for incident in selected_cluster.get("incidents", []):
            st.markdown(
                f"- {incident.get('event_id')} · {incident.get('timestamp', 'unknown')} · {incident.get('incident_type', 'unclassified')} · {incident.get('address', 'unknown')}"
            )

    with review_col:
        st.markdown("#### Review status")
        review_status = selected_cluster.get("review_status", "NEW")
        st.info(f"Current status: {review_status}")
        for label, value in [
            ("Under review", "UNDER_REVIEW"),
            ("Reviewed", "REVIEWED"),
            ("Needs further investigation", "NEEDS_FURTHER_INVESTIGATION"),
        ]:
            if st.button(label, key=f"cluster-review-{selected_cluster_id}-{value}", use_container_width=True):
                try:
                    response = requests.post(
                        f"{API_URL}/api/v1/incident-clusters/{selected_cluster_id}/review",
                        json={"status": value, "review_notes": f"Operator review: {label}"},
                        timeout=5,
                    )
                    response.raise_for_status()
                    st.success(f"Cluster status updated to {value}.")
                    st.rerun()
                except requests.RequestException as exc:
                    st.error(f"Review update failed: {exc}")


def render_crime_trends_content():
    st.markdown(
        '<div class="radar-trend-page">'
        '<p class="radar-analytics-heading">INTELLIGENCE & REPORTING</p>'
        '<h1 class="radar-page-heading">Crime Analysis</h1>'
        '<p class="radar-page-copy">Compare report activity, identify unusual '
        'changes, and review trends over matched time periods.</p></div>',
        unsafe_allow_html=True,
    )
    st.markdown(
        '<p class="radar-analytics-heading">REPORT COMPARISON</p>'
        '<p class="radar-analytics-subtitle">Matched reporting windows · '
        'UTC dates · descriptive statistics only</p>',
        unsafe_allow_html=True,
    )
    period_column, demo_column = st.columns([1.1, 2], vertical_alignment="bottom")
    with period_column:
        period_days = st.selectbox(
            "Comparison window",
            options=[7, 30, 90, 180],
            format_func=lambda days: f"Last {days} days",
            index=1,
            key="crime-trend-period",
        )
    with demo_column:
        include_demo_trends = st.checkbox(
            "Include simulated/demo records",
            value=False,
            help="Demo and training records are excluded unless explicitly enabled.",
            key="crime-trend-include-demo",
        )
    try:
        trends = load_crime_trends(period_days, include_demo_trends)
    except (requests.RequestException, ValueError, KeyError) as exc:
        st.error(f"Crime trend analytics unavailable: {exc}")
        return

    change = trends["change_percent"]
    change_label = (
        f"{change:+.1f}% vs previous period"
        if change is not None
        else "No previous-period reports"
    )
    current_column, previous_column, change_column, average_column = st.columns(4)
    current_column.metric(
        "Reports · current period",
        trends["current_count"],
        delta=change_label,
        delta_color="inverse" if change is not None else "off",
    )
    previous_column.metric("Reports · previous period", trends["previous_count"])
    change_column.metric(
        "Period-over-period change",
        f"{change:+.1f}%" if change is not None else "NEW",
        delta_color="inverse",
    )
    average_column.metric(
        "Average reports per day",
        f"{trends['average_per_day']:.2f}",
    )

    st.caption(
        f"Current: {trends['current_start']} to {trends['current_end']} · "
        f"Previous: {trends['comparison_start']} to "
        f"{trends['comparison_end']} (UTC)"
    )
    st.info(
        "This prototype has no verified live agency feed. Trends summarize "
        "stored reports, including unverified public reports; they are "
        "descriptive and are not a forecast of crime."
    )
    if include_demo_trends:
        st.warning(
            "Simulated/demo records are included in these charts and "
            "should not be interpreted as real events."
        )

    st.markdown("#### Sudden spike detection")
    st.caption(
        "A day is flagged when it has at least 3 reports and is at least "
        "2× and 3 reports above its preceding 7-day daily average. "
        "High indicates at least 5 reports and a 3× / 5-report increase. "
        "These are statistical review cues, not predictions or verified events."
    )
    spike_days = trends.get("spike_days", [])
    spike_timeline = trends.get("spike_timeline", [])
    if spike_timeline:
        spike_chart = pd.DataFrame(spike_timeline)
        spike_chart["date"] = pd.to_datetime(spike_chart["date"])
        spike_chart = spike_chart.set_index("date")
        spike_chart = spike_chart.rename(
            columns={
                "count": "Reports",
                "baseline_average": "7-day baseline",
                "spike_threshold": "Review threshold",
                "high_threshold": "High threshold",
            }
        )[
            [
                "Reports",
                "7-day baseline",
                "Review threshold",
                "High threshold",
            ]
        ]
        st.markdown("##### Daily reports vs. spike thresholds")
        st.caption(
            "The threshold lines use the same preceding 7-day baseline and "
            "criteria as the spike flags below."
        )
        st.line_chart(
            spike_chart,
            color=["#35c9dc", "#aa91ff", "#ffbf69", "#ff596d"],
            use_container_width=True,
        )

    if spike_days:
        spike_cards = []
        for spike in spike_days:
            severity = spike["severity"]
            severity_class = "elevated" if severity == "elevated" else ""
            severity_label = "Elevated" if severity == "elevated" else "High"
            spike_date = pd.to_datetime(spike["date"]).strftime("%d %b %Y")
            spike_cards.append(
                f'<div class="radar-spike-card {severity_class}">'
                '<div class="radar-spike-top">'
                f'<span class="radar-spike-date">{spike_date}</span>'
                f'<span class="radar-spike-severity">{severity_label}</span>'
                '</div>'
                f'<div class="radar-spike-count">{spike["count"]} reports</div>'
                f'<div class="radar-spike-detail">7-day baseline: '
                f'{spike["baseline_average"]:.2f} reports/day · '
                f'{spike["baseline_count"]} reports total</div></div>'
            )
        st.markdown(
            '<div class="radar-spike-grid">'
            + "".join(spike_cards)
            + "</div>",
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            '<div class="radar-no-spikes"><strong>No sudden spikes '
            'detected</strong> · Daily counts remained below the configured '
            'review thresholds for this period.</div>',
            unsafe_allow_html=True,
        )

    trend_chart_column, type_chart_column = st.columns([1.35, 1], gap="medium")
    with trend_chart_column:
        st.markdown("#### Daily reported incidents")
        daily_df = pd.DataFrame(trends["daily_counts"])
        daily_df["date"] = pd.to_datetime(daily_df["date"])
        daily_df = daily_df.set_index("date")
        daily_df["7-day average"] = daily_df["count"].rolling(
            window=7, min_periods=1
        ).mean()
        daily_df = daily_df.rename(columns={"count": "Reports"})
        st.download_button(
            "Download daily trend CSV",
            data=daily_df.to_csv(index_label="date"),
            file_name=f"crime-trends-{period_days}-days.csv",
            mime="text/csv",
            key=f"crime-trends-download-{period_days}-{include_demo_trends}",
        )
        st.line_chart(
            daily_df,
            color=["#35c9dc", "#aa91ff"],
            use_container_width=True,
        )
        busiest_day = trends["busiest_day"]
        if busiest_day and busiest_day["count"]:
            st.caption(
                f"Peak day in selected period: {busiest_day['date']} · "
                f"{busiest_day['count']} report(s)"
            )
        else:
            st.caption("No reports were recorded in the selected period.")

    with type_chart_column:
        st.markdown("#### Incident-type trend")
        if trends["incident_types"]:
            type_df = pd.DataFrame(trends["incident_types"]).head(10)
            type_df = type_df.set_index("incident_type")[
                ["current_count", "previous_count"]
            ].rename(
                columns={
                    "current_count": "Current",
                    "previous_count": "Previous",
                }
            )
            st.bar_chart(
                type_df,
                horizontal=True,
                color=["#35c9dc", "#758cff"],
            )
        else:
            st.caption("No incident types in the selected periods.")

def render_crime_trends_dashboard():
    with st.container(border=True):
        render_crime_trends_content()

@st.fragment
def render_live_dashboard():
    alert_confirmation = st.session_state.pop("station_alert_confirmation", None)
    if alert_confirmation:
        if isinstance(alert_confirmation, dict):
            notification = (
                "**DISPATCH SIMULATED · NOT SENT**\n\n"
                f"Case {escape_markdown(alert_confirmation['incident_id'])} · "
                f"{escape_markdown(alert_confirmation['incident_type'])} → "
                f"{escape_markdown(alert_confirmation['station_name'])} · "
                f"{alert_confirmation['distance_km']:.1f} km"
            )
            st.toast(notification, icon="📡")
        else:
            st.toast(str(alert_confirmation), icon="📡")

    st.markdown(
        '<p class="radar-analytics-heading">LIVE OPERATIONS</p>'
        '<h1 class="radar-page-heading">Incident command map</h1>'
        '<p class="radar-page-copy">Monitor reported activity, patrol telemetry, '
        'and station coverage across Tamil Nadu. Refresh data when you need an '
        'update; the map will stay still between refreshes.</p>',
        unsafe_allow_html=True,
    )
    st.button(
        "Refresh dashboard data",
        key="refresh-live-dashboard",
    )

    try:
        incidents_data, units_data, source_status, police_stations = asyncio.run(
            load_dashboard_data()
        )
        data_error = None
    except (requests.RequestException, ValueError, KeyError) as exc:
        incidents_data, units_data, police_stations = [], [], []
        data_error = str(exc)

    if not data_error:
        st.session_state["dashboard_incidents_for_tracking"] = incidents_data

    if data_error:
        st.error(f"Telemetry service unavailable: {data_error}")
    else:
        left_panel, map_panel, right_panel = st.columns([1.3, 3.2, 1.5], gap="small")
        with left_panel:
            st.markdown('<div class="radar-panel"><h3>Activity Snapshot</h3></div>', unsafe_allow_html=True)
            show_demo_data = st.toggle(
                "Show incidents",
                value=True,
                help="Display incidents and available patrol markers.",
            )
        incoming_df = pd.DataFrame(incidents_data)
        if not incoming_df.empty:
            incoming_df["is_demo"] = incoming_df["status"].map(is_training_status)
            incoming_df["is_report"] = (
                incoming_df["status"].astype("string").str.upper() == "PENDING_REVIEW"
            )
            agency_df = incoming_df[
                ~incoming_df["is_demo"] & ~incoming_df["is_report"]
            ].copy()
            report_df = incoming_df[incoming_df["is_report"]].copy()
            persisted_demo_df = incoming_df[incoming_df["is_demo"]].copy()
        else:
            agency_df = incoming_df
            report_df = incoming_df
            persisted_demo_df = incoming_df
        demo_df = (
            persisted_demo_df
            if show_demo_data
            else pd.DataFrame()
        )
        df = pd.concat([agency_df, report_df, demo_df], ignore_index=True)
        if not df.empty:
            training_rows = df["is_demo"].astype(bool)
            df.loc[training_rows, "event_id"] = df.loc[training_rows, "event_id"].map(
                lambda event_id: display_event_id(event_id, True)
            )
            df.loc[training_rows, "incident_type"] = df.loc[
                training_rows, "incident_type"
            ].map(lambda incident_type: display_incident_type(incident_type, True))
            df.loc[training_rows, "status"] = df.loc[training_rows, "status"].map(
                display_incident_status
            )
            df.loc[training_rows, "address"] = df.loc[training_rows, "address"].map(
                lambda address: display_incident_address(address, True)
            )
            df["_display_timestamp"] = pd.to_datetime(
                df["timestamp"], errors="coerce", utc=True
            )
            builtin_training_rows = df["event_id"].astype(str).str.startswith("TRAIN-TN-")
            df.loc[builtin_training_rows, "_display_timestamp"] = pd.Timestamp(
                "1970-01-01", tz="UTC"
            )
            df = (
                df.sort_values(
                    "_display_timestamp",
                    ascending=False,
                    na_position="last",
                    kind="stable",
                )
                .drop(columns="_display_timestamp")
                .reset_index(drop=True)
            )
        incident_ids = df["event_id"].astype(str).tolist() if not df.empty else []
        incident_action_queue = st.session_state.get("incident_action_queue")
        new_report_ids = []
        if incident_action_queue is None:
            incident_action_queue = incident_ids.copy()
            st.session_state["incident_action_queue"] = incident_action_queue
            st.session_state["known_action_incident_ids"] = set(incident_ids)
            st.session_state["released_action_incident_ids"] = set(
                incident_action_queue[:1]
            )
        else:
            known_action_incident_ids = st.session_state.setdefault(
                "known_action_incident_ids", set(incident_action_queue)
            )
            released_action_incident_ids = st.session_state.setdefault(
                "released_action_incident_ids", set(incident_action_queue[:1])
            )
            new_incident_ids = [
                event_id for event_id in incident_ids
                if event_id not in known_action_incident_ids
            ]
            new_report_ids = [
                str(incident["event_id"])
                for incident in df.loc[df["is_report"]].to_dict(orient="records")
                if str(incident["event_id"]) in new_incident_ids
            ]
            if incident_action_queue:
                incident_action_queue[1:1] = new_report_ids
            else:
                incident_action_queue.extend(new_report_ids)
            incident_action_queue.extend(
                event_id for event_id in new_incident_ids
                if event_id not in new_report_ids
            )
            known_action_incident_ids.update(new_incident_ids)
        live_incident_ids = set(incident_ids)
        incident_action_queue[:] = [
            event_id
            for event_id in incident_action_queue
            if event_id in live_incident_ids
        ]
        if not st.session_state.get("action_queue_prioritized_for_map"):
            report_ids = (
                set(df.loc[df["is_report"], "event_id"].astype(str))
                if not df.empty
                else set()
            )
            new_report_ids = set(new_report_ids)
            pending_ids = incident_action_queue[1:]
            incident_action_queue[1:] = (
                [event_id for event_id in pending_ids if event_id in new_report_ids]
                + [
                    event_id
                    for event_id in pending_ids
                    if event_id not in report_ids and event_id not in new_report_ids
                ]
                + [
                    event_id
                    for event_id in pending_ids
                    if event_id in report_ids and event_id not in new_report_ids
                ]
            )
            st.session_state["action_queue_prioritized_for_map"] = True
        released_action_incident_ids = st.session_state.setdefault(
            "released_action_incident_ids", set(incident_action_queue[:1])
        )
        previous_incidents = st.session_state.get("previous_action_incidents")
        if previous_incidents is None:
            queued_ids = set(incident_action_queue)
            known_ids = st.session_state.get("known_action_incident_ids", set())
            sent_ids = {
                item["incident_id"]
                for item in st.session_state.get("station_alert_outbox", [])
            }
            previous_incidents = [
                incident
                for incident in df.to_dict(orient="records")
                if str(incident["event_id"]) in known_ids
                and str(incident["event_id"]) not in queued_ids
                and str(incident["event_id"]) not in sent_ids
            ]
            st.session_state["previous_action_incidents"] = previous_incidents
        now = time.monotonic()
        last_rotation_at = st.session_state.setdefault(
            "last_auto_case_rotation_at", now
        )
        if now - last_rotation_at >= CASE_ROTATION_SECONDS:
            st.session_state["last_auto_case_rotation_at"] = now
            if incident_action_queue:
                previous_incident_id = incident_action_queue.pop(0)
                previous_matches = df.loc[
                    df["event_id"].astype(str).eq(previous_incident_id)
                ]
                previous_incidents = st.session_state.setdefault(
                    "previous_action_incidents", []
                )
                if not previous_matches.empty and not any(
                    str(item["event_id"]) == previous_incident_id
                    for item in previous_incidents
                ):
                    previous_incidents.append(
                        previous_matches.iloc[0].to_dict()
                    )
                    del previous_incidents[:-50]
            if incident_action_queue:
                released_action_incident_ids.add(incident_action_queue[0])

        current_critical = (
            df.loc[df["priority"].astype("string").str.upper().eq("CRITICAL")]
            .to_dict(orient="records")
            if not df.empty
            else []
        )
        current_critical_ids = {str(incident["event_id"]) for incident in current_critical}
        alert_case_queue = st.session_state.get("critical_alert_case_queue")
        observed_critical_ids = st.session_state.get("observed_critical_incident_ids")
        if alert_case_queue is None or observed_critical_ids is None:
            alert_case_queue = [
                str(incident["event_id"]) for incident in current_critical
            ]
            observed_critical_ids = current_critical_ids.copy()
        else:
            alert_case_queue = [
                event_id
                for event_id in alert_case_queue
                if event_id in current_critical_ids
            ]
            newly_observed_critical_ids = [
                str(incident["event_id"])
                for incident in current_critical
                if str(incident["event_id"]) not in observed_critical_ids
            ]
            alert_case_queue.extend(newly_observed_critical_ids)
            observed_critical_ids.update(current_critical_ids)
        st.session_state["critical_alert_case_queue"] = alert_case_queue
        st.session_state["observed_critical_incident_ids"] = observed_critical_ids

        simulated_units = [
            unit
            for unit in units_data
            if show_demo_data or not is_training_status(unit["status"])
        ]

        demo_critical_incidents = (
            df.loc[df["is_demo"] & df["priority"].astype("string").str.upper().eq("CRITICAL")]
            .to_dict(orient="records")
            if not df.empty
            else []
        )
        unit_by_id = {str(unit["unit_id"]): unit for unit in simulated_units}
        station_by_id = {
            station["station_id"]: station for station in police_stations
        }
        active_incident_ids = {
            str(incident["event_id"]) for incident in demo_critical_incidents
        }
        existing_manual_assignments = st.session_state.get(
            "manual_training_dispatch_assignments", {}
        )
        manual_assignments = {}
        used_unit_ids = set()
        for event_id, assignment in existing_manual_assignments.items():
            event_id = str(event_id)
            station_id = str(assignment.get("station_id", ""))
            unit_id = str(assignment.get("unit_id", ""))
            if (
                event_id in active_incident_ids
                and station_id in station_by_id
                and unit_id in unit_by_id
                and unit_id not in used_unit_ids
            ):
                manual_assignments[event_id] = {
                    "station_id": station_id,
                    "unit_id": unit_id,
                }
                used_unit_ids.add(unit_id)
        st.session_state["manual_training_dispatch_assignments"] = manual_assignments

        existing_assignments = st.session_state.get("demo_dispatch_assignments", {})
        assignments = {
            event_id: assignment["unit_id"]
            for event_id, assignment in manual_assignments.items()
        }
        for event_id, unit_id in existing_assignments.items():
            event_id = str(event_id)
            unit_id = str(unit_id)
            if (
                event_id in active_incident_ids
                and event_id not in assignments
                and unit_id in unit_by_id
                and unit_id not in used_unit_ids
            ):
                assignments[event_id] = unit_id
                used_unit_ids.add(unit_id)

        unassigned_incidents = [
            incident
            for incident in demo_critical_incidents
            if str(incident["event_id"]) not in assignments
        ]
        available_units = [
            unit for unit_id, unit in unit_by_id.items() if unit_id not in used_unit_ids
        ]
        station_by_unit_id = {
            station["unit_id"]: station for station in police_stations
        }

        def station_distance(unit, incident):
            station = station_by_unit_id.get(str(unit["unit_id"]), unit)
            return haversine(
                station["longitude"],
                station["latitude"],
                incident["longitude"],
                incident["latitude"],
            )

        candidate_assignments = sorted(
            (
                station_distance(unit, incident),
                str(incident["event_id"]),
                str(unit["unit_id"]),
            )
            for incident in unassigned_incidents
            for unit in available_units
        )
        for _, event_id, unit_id in candidate_assignments:
            if event_id not in assignments and unit_id not in used_unit_ids:
                assignments[event_id] = unit_id
                used_unit_ids.add(unit_id)

        st.session_state["demo_dispatch_assignments"] = assignments
        dispatch_by_incident = {}
        for incident in current_critical:
            event_id = str(incident["event_id"])
            unit_id = assignments.get(event_id)
            if unit_id is not None:
                unit = unit_by_id[unit_id]
                manual_assignment = manual_assignments.get(event_id)
                station = (
                    station_by_id[manual_assignment["station_id"]]
                    if manual_assignment
                    else next(
                        (
                            item
                            for item in police_stations
                            if item["unit_id"] == unit_id
                        ),
                        None,
                    )
                )
                if station is None:
                    station, _ = nearest_training_station(
                        incident["latitude"], incident["longitude"], police_stations
                    )
                dispatch_by_incident[event_id] = {
                    "unit": unit,
                    "distance_km": haversine(
                        unit["longitude"],
                        unit["latitude"],
                        incident["longitude"],
                        incident["latitude"],
                    ),
                    "station": station,
                    "station_distance_km": (
                        haversine(
                            station["longitude"],
                            station["latitude"],
                            incident["longitude"],
                            incident["latitude"],
                        )
                        if station is not None
                        else None
                    ),
                    "nearby_stations": nearest_training_stations(
                        incident["latitude"],
                        incident["longitude"],
                        police_stations,
                        max_count=1,
                        exclude_station_id=station["station_id"] if station else None,
                    ),
                    "manual": event_id in manual_assignments,
                }
            else:
                station, station_distance_km = nearest_training_station(
                    incident["latitude"], incident["longitude"], police_stations
                )
                nearby_stations = nearest_training_stations(
                    incident["latitude"],
                    incident["longitude"],
                    police_stations,
                    max_count=1,
                    exclude_station_id=station["station_id"] if station else None,
                )
                dispatch_by_incident[event_id] = {
                    "unit": None,
                    "distance_km": None,
                    "station": station,
                    "station_distance_km": station_distance_km,
                    "nearby_stations": nearby_stations,
                    "manual": False,
                }
            dispatch_by_incident[event_id]["manual"] = (
                event_id in manual_assignments
            )

        incident_types = sorted(df["incident_type"].dropna().unique()) if not df.empty else []
        priorities = sorted(df["priority"].dropna().unique()) if not df.empty else []
        incident_statuses = (
            sorted(df["status"].dropna().astype(str).unique()) if not df.empty else []
        )
        if not df.empty:
            available_timestamps = pd.to_datetime(
                df["timestamp"], errors="coerce", utc=True
            ).dropna()
        else:
            available_timestamps = pd.Series(dtype="datetime64[ns, UTC]")
        if available_timestamps.empty:
            date_min = date_max = datetime.now(timezone.utc).date()
        else:
            date_min = available_timestamps.min().date()
            date_max = available_timestamps.max().date()
        area_options = sorted(
            {
                str(address).split(",", 1)[0].strip()
                for address in df["address"].dropna()
            }
        ) if not df.empty else []

        critical_count = (
            int((df["priority"].str.upper() == "CRITICAL").sum())
            if not df.empty
            else 0
        )
        real_count = (
            int((~df["is_demo"] & ~df["is_report"]).sum())
            if not df.empty
            else 0
        )
        report_count = int(df["is_report"].sum()) if not df.empty else 0
        demo_critical_count = (
            int(((df["priority"].str.upper() == "CRITICAL") & df["is_demo"]).sum())
            if not df.empty
            else 0
        )
        real_critical_count = critical_count - demo_critical_count

        overview_columns = st.columns(4)
        overview_columns[0].metric("Incidents in view", len(df))
        overview_columns[1].metric("Critical priority", critical_count)
        overview_columns[2].metric("Public reports", report_count)
        overview_columns[3].metric("Police stations", len(police_stations))
        st.caption(
            "Live agency data is not connected. Counts may include unverified "
            "public reports or simulated training records."
        )

        left_panel, map_panel, right_panel = st.columns(
            [1.3, 3.4, 1.3], gap="small"
        )
        with left_panel:
            st.markdown(
                '<div class="radar-panel"><h3>Operations summary</h3></div>',
                unsafe_allow_html=True,
            )
            st.metric(
                "Priority monitor",
                "REVIEW" if critical_count else "NOMINAL",
                delta=f"{critical_count} critical-priority record(s)",
                delta_color="inverse" if critical_count else "off",
            )
            real_critical_count = critical_count - demo_critical_count
            report_timestamps = (
                pd.to_datetime(df["timestamp"], errors="coerce", utc=True)
                if not df.empty
                else pd.Series(dtype="datetime64[ns, UTC]")
            )
            now_utc = pd.Timestamp.now(tz="UTC")
            recent_24h = report_timestamps.ge(now_utc - pd.Timedelta(hours=24))
            recent_count = int(recent_24h.sum())
            st.metric("Incidents", len(df))
            st.metric("Critical", int((df["priority"].str.upper() == "CRITICAL").sum()) if not df.empty else 0)
            latest_types = (
                df.loc[recent_24h, "incident_type"].value_counts()
                if not df.empty and recent_count
                else pd.Series(dtype=int)
            )
            peak_type = str(latest_types.index[0]) if not latest_types.empty else "Awaiting incidents"
            st.markdown(
                f'<div class="radar-zone"><small>Top crime type · last 24h</small><br>'
                f'<strong>{html.escape(peak_type)}</strong></div>',
                unsafe_allow_html=True,
            )
            latest_incident = df.iloc[0] if not df.empty else None
            latest_incident_type = (
                display_incident_type(
                    latest_incident["incident_type"],
                    bool(latest_incident["is_demo"]),
                )
                if latest_incident is not None
                else "Awaiting telemetry"
            )
            st.markdown(
                f"**Latest incident:** "
                f"{html.escape(latest_incident_type)}"
            )
            st.caption(
                f"Agency: {real_count} · Submitted: {report_count} · "
                f"Critical: {critical_count} · Auto-refresh active"
            )

        with left_panel:
            st.markdown(
                '<div class="radar-panel"><h3>Filters & Layers</h3></div>', unsafe_allow_html=True)
            address_search = st.text_input(
                "Search address",
                placeholder="Search address or area",
                key="incident-address-search",
            )
            selected_date_range = st.date_input(
                "Date range",
                value=(date_min, date_max),
                min_value=date_min,
                max_value=date_max,
                key="incident-date-range",
            )
            selected_time_window = st.selectbox(
                "Time",
                ["All day", "18:00-06:00", "06:00-12:00", "12:00-18:00"],
                key="incident-time-window",
            )
            selected_area = st.selectbox(
                "Location",
                ["All areas", *area_options],
                key="incident-area-filter",
            )
            selected_type = st.selectbox("Crime type", ["All types", *incident_types])
            selected_priority = st.selectbox("Priority", ["All priorities", *priorities])
            selected_status = st.selectbox("Status", ["All statuses", *incident_statuses])
            show_heatmap = st.checkbox("Incident heat layer", value=False)
            show_patrol_units = st.checkbox("Show patrol telemetry", value=True)

        filtered_df = df.copy()
        if len(selected_date_range) == 2:
            range_start = pd.Timestamp(selected_date_range[0], tz="UTC")
            range_end = pd.Timestamp(
                selected_date_range[1] + timedelta(days=1), tz="UTC"
            )
            incident_times = pd.to_datetime(
                filtered_df["timestamp"], errors="coerce", utc=True
            )
            filtered_df = filtered_df.loc[
                incident_times.ge(range_start) & incident_times.lt(range_end)
            ]
        incident_times = pd.to_datetime(
            filtered_df["timestamp"], errors="coerce", utc=True
        )
        incident_hours = incident_times.dt.hour
        if selected_time_window == "18:00-06:00":
            filtered_df = filtered_df.loc[
                incident_hours.ge(18) | incident_hours.lt(6)
            ]
        elif selected_time_window == "06:00-12:00":
            filtered_df = filtered_df.loc[
                incident_hours.ge(6) & incident_hours.lt(12)
            ]
        elif selected_time_window == "12:00-18:00":
            filtered_df = filtered_df.loc[
                incident_hours.ge(12) & incident_hours.lt(18)
            ]
        if selected_area != "All areas":
            incident_areas = (
                filtered_df["address"]
                .astype("string")
                .str.split(",", n=1)
                .str[0]
                .str.strip()
            )
            filtered_df = filtered_df.loc[incident_areas.eq(selected_area)]
        if selected_type != "All types":
            filtered_df = filtered_df[filtered_df["incident_type"] == selected_type]
        if selected_priority != "All priorities":
            filtered_df = filtered_df[filtered_df["priority"] == selected_priority]
        if selected_status != "All statuses":
            filtered_df = filtered_df[filtered_df["status"].astype(str) == selected_status]
        if address_search.strip():
            filtered_df = filtered_df[
                filtered_df["address"]
                .astype("string")
                .str.contains(address_search.strip(), case=False, regex=False, na=False)
            ]

        current_alert_id = alert_case_queue[0] if alert_case_queue else None
        current_alert_incident = (
            next(
                (
                    incident
                    for incident in current_critical
                    if str(incident["event_id"]) == current_alert_id
                ),
                None,
            )
            if current_alert_id is not None
            else None
        )
        map_df = filtered_df.copy()
        if not map_df.empty:
            staged_incidents = map_df["is_demo"].astype(bool)
            released_staged_incidents = map_df["event_id"].astype(str).isin(
                released_action_incident_ids
            )
            map_df = map_df.loc[
                ~staged_incidents | released_staged_incidents
            ].copy()
        active_action_incident_id = (
            str(incident_action_queue[0]) if incident_action_queue else None
        )
        if not df.empty:
            visible_report_ids = set(
                map_df.loc[map_df["is_report"], "event_id"].astype(str)
            )
            new_report_rows = df.loc[
                df["is_report"] & ~df["event_id"].astype(str).isin(visible_report_ids)
            ]
            if not new_report_rows.empty:
                map_df = pd.concat([map_df, new_report_rows], ignore_index=True)
        if (
            active_action_incident_id is not None
            and not df.empty
            and not map_df["event_id"].astype(str).eq(active_action_incident_id).any()
        ):
            active_rows = df[df["event_id"].astype(str) == active_action_incident_id]
            if not active_rows.empty and (
                not bool(active_rows.iloc[0]["is_demo"])
                or active_action_incident_id in released_action_incident_ids
            ):
                map_df = pd.concat([map_df, active_rows], ignore_index=True)
        critical_df = filtered_df[filtered_df["priority"].str.upper() == "CRITICAL"] if not filtered_df.empty else filtered_df
        target = critical_df.iloc[0] if not critical_df.empty else (filtered_df.iloc[0] if not filtered_df.empty else None)

        with left_panel:
            if real_critical_count:
                st.markdown(
                    f'<div class="radar-alert">AGENCY ALERT: {real_critical_count} critical '
                    f'incident{"s" if real_critical_count != 1 else ""}</div>',
                    unsafe_allow_html=True,
                )
            if demo_critical_count:
                st.markdown(
                    f'<div class="radar-live-alert">CRITICAL REPORTS: {demo_critical_count} '
                    f'critical event{"s" if demo_critical_count != 1 else ""}</div>',
                    unsafe_allow_html=True,
                )
            st.markdown('<div class="radar-panel"><h3>Map Legend</h3><small>State outline · Tamil Nadu jurisdiction<br>'
                        'Heat glow · incident density<br>'
                        'Red dot / cluster · incidents<br>'
                        'Blue PD badge · police station<br>'
                        'Blue marker · received patrol asset</small></div>', unsafe_allow_html=True)
        with map_panel:
            toolbar_city, toolbar_scope = st.columns([2, 1])
            with toolbar_city:
                city_centers = {
                    "Tamil Nadu": [10.8, 78.2],
                    "Chennai": [13.0827, 80.2707],
                    "Coimbatore": [11.0168, 76.9558],
                    "Madurai": [9.9252, 78.1198],
                    "Salem": [11.6643, 78.1460],
                    "Tiruchirappalli": [10.7905, 78.7047],
                    "Tirunelveli": [8.7139, 77.7567],
                    "Erode": [11.3410, 77.7172],
                    "Vellore": [12.9165, 79.1325],
                    "Tiruppur": [11.1085, 77.3411],
                    "Thanjavur": [10.7870, 79.1378],
                    "Cuddalore": [11.7480, 79.7714],
                    "Thoothukudi": [8.7642, 78.1348],
                    "Nagercoil": [8.1833, 77.4119],
                    "Dindigul": [10.3673, 77.9803],
                    "Hosur": [12.7409, 77.8253],
                    "Kanchipuram": [12.8342, 79.7036],
                    "Karur": [10.9601, 78.0766],
                    "Ramanathapuram": [9.3639, 78.8395],
                    "Pudukkottai": [10.3833, 78.8001],
                }
                map_city = st.selectbox(
                    "Map focus", list(city_centers), index=1,
                    label_visibility="collapsed", key="map-city-focus-v2"
                )
            with toolbar_scope:
                status_text = (
                    f"TAMIL NADU · {report_count} USER REPORTS"
                    if show_demo_data
                    else "TAMIL NADU · AGENCY DATA"
                )
                st.markdown(
                    f'<p class="radar-no-feed">{status_text}</p>',
                    unsafe_allow_html=True,
                )
            if real_critical_count:
                st.markdown(
                    f'<div class="radar-alert">⚠ AGENCY ALERT: {real_critical_count} critical '
                    f'incident{"s" if real_critical_count != 1 else ""} in received telemetry</div>',
                    unsafe_allow_html=True,
                )
            elif demo_critical_count:
                st.markdown(
                    f'<div class="radar-live-alert">⚠ '
                    f'{demo_critical_count} critical events</div>',
                    unsafe_allow_html=True,
                )
            elif not filtered_df.empty:
                st.markdown(
                    f'<div class="radar-live-alert">● {len(filtered_df)} matching report(s) · '
                    'See agency feed status above</div>',
                    unsafe_allow_html=True,
                )
            else:
                st.markdown(
                    '<div class="radar-live-alert">● NO MATCHING INCIDENT REPORTS · '
                    'Awaiting authorized agency reports</div>',
                    unsafe_allow_html=True,
                )

            boundary_coordinates = [
                point
                for polygon in TAMIL_NADU_FEATURE["geometry"]["coordinates"]
                for point in polygon[0]
            ]
            south = min(point[1] for point in boundary_coordinates)
            west = min(point[0] for point in boundary_coordinates)
            north = max(point[1] for point in boundary_coordinates)
            east = max(point[0] for point in boundary_coordinates)
            map_min_zoom = 11
            map_home_zoom = 13
            jurisdiction_bounds = [
                [south - 0.1, west - 0.1],
                [north + 0.1, east + 0.1],
            ]
            selected_map_incident_id = st.session_state.get("map_focus_event_id")
            selected_map_incident_rows = (
                df.loc[
                    df["event_id"].astype(str).eq(str(selected_map_incident_id))
                ]
                if selected_map_incident_id is not None and not df.empty
                else pd.DataFrame()
            )
            selected_map_incident = (
                selected_map_incident_rows.iloc[0].to_dict()
                if not selected_map_incident_rows.empty
                else None
            )
            if selected_map_incident is None and selected_map_incident_id is not None:
                selected_map_incident = next(
                    (
                        incident
                        for incident in st.session_state.get(
                            "previous_action_incidents", []
                        )
                        if str(incident["event_id"]) == str(selected_map_incident_id)
                    ),
                    None,
                )
            nearby_map_stations = (
                nearest_training_stations(
                    float(selected_map_incident["latitude"]),
                    float(selected_map_incident["longitude"]),
                    police_stations,
                    max_count=5,
                    max_distance_km=35,
                )
                if selected_map_incident is not None
                else []
            )
            nearest_map_station = nearby_map_stations[0][0] if nearby_map_stations else None
            map_selection = None
            if selected_map_incident is not None:
                is_demo = bool(
                    selected_map_incident.get(
                        "is_demo",
                        is_training_status(selected_map_incident.get("status", "")),
                    )
                )
                incident_name = html.escape(
                    display_incident_type(
                        selected_map_incident["incident_type"], is_demo
                    )
                )
                incident_address = html.escape(
                    display_incident_address(selected_map_incident["address"], is_demo)
                )
                map_selection = {
                    "incident": {
                        "latitude": float(selected_map_incident["latitude"]),
                        "longitude": float(selected_map_incident["longitude"]),
                        "popup_html": (
                            f"<b>{incident_name}</b><br>"
                            f"<b>Area:</b> {incident_address}<br>"
                            f"<b>Reported:</b> "
                            f"{html.escape(display_incident_time(selected_map_incident.get('timestamp')))}"
                        ),
                    },
                    "stations": [
                        {
                            "latitude": float(station["latitude"]),
                            "longitude": float(station["longitude"]),
                            "name": str(station["name"]),
                            "popup_html": (
                                f"<b>{html.escape(str(station['name']))}</b><br>"
                                f"{html.escape(str(station['name']))} · "
                                f"{station_distance:.2f} km from selected incident"
                            ),
                        }
                        for station, station_distance in nearby_map_stations
                    ],
                }
            map_center = city_centers[map_city]
            map_zoom = map_home_zoom
            radar_map = folium.Map(
                location=map_center,
                zoom_start=map_zoom,
                minZoom=map_min_zoom,
                max_zoom=18,
                tiles=None,
                control_scale=True,
                max_bounds=True,
                min_lat=floor(jurisdiction_bounds[0][0]),
                max_lat=ceil(jurisdiction_bounds[1][0]),
                min_lon=floor(jurisdiction_bounds[0][1]),
                max_lon=ceil(jurisdiction_bounds[1][1]),
                maxBoundsViscosity=1.0,
            )
            folium.TileLayer(
                tiles="https://server.arcgisonline.com/ArcGIS/rest/services/"
                "Canvas/World_Dark_Gray_Base/MapServer/tile/{z}/{y}/{x}",
                attr="Tiles © Esri — Sources: Esri, HERE, Garmin, USGS, "
                "OpenStreetMap contributors, and the GIS User Community",
                name="Dark street map",
                max_zoom=16,
                max_native_zoom=16,
                show=True,
            ).add_to(radar_map)
            folium.TileLayer(
                tiles="https://server.arcgisonline.com/ArcGIS/rest/services/"
                "World_Street_Map/MapServer/tile/{z}/{y}/{x}",
                attr="Tiles © Esri — Sources: Esri, HERE, Garmin, USGS, "
                "OpenStreetMap contributors, and the GIS User Community",
                name="Grayscale street detail",
                max_zoom=18,
                max_native_zoom=18,
                show=False,
            ).add_to(radar_map)
            folium.TileLayer(
                tiles="https://server.arcgisonline.com/ArcGIS/rest/services/"
                "Canvas/World_Dark_Gray_Reference/MapServer/tile/{z}/{y}/{x}",
                attr="Labels © Esri",
                name="Place labels",
                max_zoom=16,
                max_native_zoom=16,
                overlay=True,
                show=True,
            ).add_to(radar_map)
            if selected_map_incident is not None and nearest_map_station is not None:
                incident_point = [
                    float(selected_map_incident["latitude"]),
                    float(selected_map_incident["longitude"]),
                ]
                station_point = [
                    float(nearest_map_station["latitude"]),
                    float(nearest_map_station["longitude"]),
                ]
                folium.PolyLine([incident_point, station_point], color="#51d6ff", weight=2.5, opacity=0.95).add_to(radar_map)
            TacticalTileStyle().add_to(radar_map.get_root())
            outside_mask = {
                "type": "Feature",
                "properties": {"name": "Outside Tamil Nadu"},
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [
                        [
                            [west - 15, south - 12],
                            [east + 15, south - 12],
                            [east + 15, north + 12],
                            [west - 15, north + 12],
                            [west - 15, south - 12],
                        ],
                        *[
                            polygon[0]
                            for polygon in TAMIL_NADU_FEATURE["geometry"]["coordinates"]
                        ],
                    ],
                },
            }
            folium.GeoJson(
                outside_mask,
                name="Outside Tamil Nadu",
                style_function=lambda _: {
                    "color": "#0b0e12",
                    "weight": 0,
                    "fillColor": "#0b0e12",
                    "fillOpacity": 1,
                    "fillRule": "evenodd",
                },
                control=False,
            ).add_to(radar_map)
            heat_points = [
                [
                    float(incident["latitude"]),
                    float(incident["longitude"]),
                    1.8
                    if str(incident["priority"]).upper() == "CRITICAL"
                    else 1.0,
                ]
                for incident in map_df.to_dict(orient="records")
            ]
            if heat_points and show_heatmap:
                HeatMap(
                    heat_points,
                    name="Incident intensity",
                    min_opacity=0.28,
                    max_zoom=13,
                    radius=30,
                    blur=26,
                    gradient={
                        0.18: "#174d9b",
                        0.38: "#19b8d1",
                        0.6: "#e4e34f",
                        0.78: "#ff913b",
                        1.0: "#ff3e43",
                    },
                    control=False,
                    show=True,
                ).add_to(radar_map)
            folium.GeoJson(
                TAMIL_NADU_FEATURE,
                name="Tamil Nadu boundary",
                style_function=lambda _: {
                    "color": "#f6c453",
                    "weight": 2.5,
                    "fillColor": "#063d4c",
                    "fillOpacity": 0.16,
                },
            ).add_to(radar_map)
            route_reference_id = (
                st.session_state.get("route-planner-incident")
                or active_action_incident_id
            )
            route_reference_rows = (
                df.loc[
                    df["event_id"].astype(str).eq(str(route_reference_id))
                ]
                if route_reference_id is not None and not df.empty
                else pd.DataFrame()
            )
            route_reference = (
                route_reference_rows.iloc[0].to_dict()
                if not route_reference_rows.empty
                else None
            )
            if route_reference is None:
                route_reference = next(
                    (
                        incident
                        for incident in st.session_state.get(
                            "previous_action_incidents", []
                        )
                        if str(incident["event_id"]) == str(route_reference_id)
                    ),
                    None,
                )
            incident_area_station_ids = set()
            route_plan_specs = []
            route_station_by_id = {}
            road_routes = {}
            route_errors = {}
            route_coordinates_shared = st.session_state.get(
                "route-sharing-consent", False
            )
            if route_reference is not None:
                nearby_incident_stations = nearest_training_stations(
                    float(route_reference["latitude"]),
                    float(route_reference["longitude"]),
                    police_stations,
                    max_distance_km=35,
                )
                incident_area_station_ids = {
                    station["station_id"] for station, _ in nearby_incident_stations
                }
                if nearby_incident_stations:
                    route_station_by_id = {
                        str(station["station_id"]): station
                        for station, _ in nearby_incident_stations
                    }
                    route_station_ids = list(route_station_by_id)
                    route_station_key = f"route-station-{route_reference_id}"
                    selected_route_station_id = str(
                        st.session_state.get(route_station_key, route_station_ids[0])
                    )
                    if selected_route_station_id not in route_station_by_id:
                        selected_route_station_id = route_station_ids[0]
                    route_plan_specs.append(
                        (selected_route_station_id, "#a7f06a", None)
                    )
                    comparison_station_ids = [
                        station_id
                        for station_id in route_station_ids
                        if station_id != selected_route_station_id
                    ]
                    if comparison_station_ids:
                        comparison_key = (
                            f"route-compare-{route_reference_id}-"
                            f"{selected_route_station_id}"
                        )
                        comparison_station_id = str(
                            st.session_state.get(
                                comparison_key, comparison_station_ids[0]
                            )
                        )
                        if comparison_station_id not in comparison_station_ids:
                            comparison_station_id = comparison_station_ids[0]
                        route_plan_specs.append(
                            (comparison_station_id, "#ffbf54", "8, 6")
                        )
                    if route_coordinates_shared:
                        for station_id, _, _ in route_plan_specs:
                            destination_station = route_station_by_id[station_id]
                            try:
                                road_routes[station_id] = get_road_route(
                                    float(destination_station["latitude"]),
                                    float(destination_station["longitude"]),
                                    float(route_reference["latitude"]),
                                    float(route_reference["longitude"]),
                                )
                            except (
                                requests.RequestException,
                                ValueError,
                                KeyError,
                                TypeError,
                            ):
                                route_errors[station_id] = (
                                    "Road distance and ETA are unavailable."
                                )
            incident_targets = (
                filtered_df.loc[
                    ~filtered_df["is_demo"] & ~filtered_df["is_report"]
                ].to_dict(orient="records")
                if not filtered_df.empty
                else []
            )
            displayed_units = units_data + (
                [unit for unit in simulated_units if unit not in units_data]
                if show_demo_data
                else []
            )
            if show_patrol_units:
                for unit in displayed_units:
                    unit_location = [unit["latitude"], unit["longitude"]]
                    unit_status = str(unit["status"])
                    is_demo_unit = is_training_status(unit_status)
                    is_available = unit_status.strip().upper() == "AVAILABLE"
                    unit_popup = (
                        f"{html.escape(unit['unit_id'])}<br>"
                        f"Status: {html.escape(display_patrol_status(unit_status))}"
                    )
                    unit_tooltip = (
                        html.escape(str(unit["unit_id"]).replace("SIM-TN-UNIT-", "UNIT-"))
                    )
                    assigned_to = next(
                        (
                            event_id
                            for event_id, assigned_unit_id in assignments.items()
                            if assigned_unit_id == str(unit["unit_id"])
                        ),
                        None,
                    )
                    if is_available and not is_demo_unit and incident_targets:
                        assigned_incident = min(
                            incident_targets,
                            key=lambda incident: haversine(
                                unit["longitude"],
                                unit["latitude"],
                                incident["longitude"],
                                incident["latitude"],
                            ),
                        )
                        distance = haversine(
                            assigned_incident["longitude"],
                            assigned_incident["latitude"],
                            unit["longitude"],
                            unit["latitude"],
                        )
                        unit_popup += f"<br>Intercept distance: {distance:.2f} km"
                        unit_tooltip += f" · {distance:.1f} km"
                    elif is_demo_unit and assigned_to:
                        assigned_incident = next(
                            incident
                            for incident in demo_critical_incidents
                            if str(incident["event_id"]) == assigned_to
                        )
                        distance = haversine(
                            assigned_incident["longitude"],
                            assigned_incident["latitude"],
                            unit["longitude"],
                            unit["latitude"],
                        )
                        unit_popup += (
                            f"<br>ASSIGNED TO: {html.escape(display_event_id(assigned_to, True))}"
                            f"<br>Distance: {distance:.2f} km"
                        )
                        unit_tooltip += f" · ASSIGNED · {distance:.1f} km"
                    patrol_marker = folium.Marker(
                        location=unit_location,
                        popup=unit_popup,
                        tooltip=unit_tooltip,
                        icon=folium.Icon(color="blue", icon="shield", prefix="fa"),
                    ).add_to(radar_map)

            if show_patrol_units and displayed_units:
                st.caption(f"Displaying {len(displayed_units)} patrol marker(s).")
            elif show_patrol_units:
                st.caption("No recent patrol telemetry received.")
            components.html(
                training_map_sync_html(map_selection),
                height=0,
                scrolling=False,
            )
            MapFocusWatcher(
                map_city,
                map_center,
                map_zoom,
                map_min_zoom,
                jurisdiction_bounds,
            ).add_to(radar_map)

            map_signature = json.dumps(
                {
                    "map_mode": "incremental-training-v21",
                    "city": map_city,
                    "show_training": show_demo_data,
                    "show_patrol_units": show_patrol_units,
                    "route_incident": route_reference_id,
                    "route_coordinates_shared": route_coordinates_shared,
                    "heat_points": heat_points,
                    "route_stations": [
                        station_id
                        for station_id, _, _ in route_plan_specs
                    ],
                    "route_errors": route_errors,
                },
                sort_keys=True,
                default=str,
            )
            if st.session_state.get("tactical_map_signature") != map_signature:
                st.session_state["tactical_map_signature"] = map_signature
                st.session_state["tactical_map_html"] = radar_map.get_root().render()
            components.html(
                st.session_state["tactical_map_html"],
                height=700,
                scrolling=False,
            )
            st.caption(
                f"Boundary: [geoBoundaries India ADM1 · Tamil Nadu]"
                f"({source_status['boundary_url']}) · {source_status['boundary_license']}"
            )
            if selected_map_incident is None:
                st.caption(
                    "Tamil Nadu view · Police station markers are hidden. Select "
                    "“Show incident and nearby stations” on a case to reveal its "
                    "exact location and nearby stations."
                )
            else:
                st.caption(
                    f"Selected incident · {float(selected_map_incident['latitude']):.5f}, "
                    f"{float(selected_map_incident['longitude']):.5f} · "
                    f"{len(nearby_map_stations)} nearby police station marker(s). "
                    "Choose “Clear map selection” on the case to hide them."
                )

        with right_panel:
            if not filtered_df.empty:
                area_frame = filtered_df.assign(
                    _activity_area=(
                        filtered_df["address"]
                        .astype("string")
                        .str.split(",", n=1)
                        .str[0]
                        .str.strip()
                    )
                )
                cluster_counts = (
                    area_frame.groupby(["_activity_area", "incident_type"])
                    .size()
                    .sort_values(ascending=False)
                    .head(3)
                )
                critical_rows = area_frame.loc[
                    area_frame["priority"].astype("string").str.upper().eq("CRITICAL")
                ]
                if not critical_rows.empty:
                    leading_critical = (
                        critical_rows.groupby(["_activity_area", "incident_type"])
                        .size()
                        .sort_values(ascending=False)
                    )
                    (critical_area, critical_type), critical_total = leading_critical.index[0], int(leading_critical.iloc[0])
                    st.markdown(
                        f'<div class="radar-alert">ALERT · '
                        f'{html.escape(str(critical_type))} · '
                        f'{html.escape(str(critical_area))} · {critical_total}</div>',
                        unsafe_allow_html=True,
                    )
                st.markdown('<div class="radar-panel"><h3>Filtered Clusters</h3></div>', unsafe_allow_html=True)
                for (activity_area, incident_type), count in cluster_counts.items():
                    st.markdown(
                        f'<div class="radar-cluster-card">'
                        f'<span class="radar-cluster-count">{int(count)}</span>'
                        f'<strong>{html.escape(str(activity_area))}</strong><br>'
                        f'<small>{html.escape(str(incident_type))}</small></div>',
                        unsafe_allow_html=True,
                    )
            else:
                st.caption("No incidents match the current filters.")
            st.markdown('<div class="radar-panel"><h3>Incident Alerts</h3></div>', unsafe_allow_html=True)
            active_incident_id = (
                incident_action_queue[0] if incident_action_queue else None
            )
            active_matches = (
                df.loc[df["event_id"].astype(str).eq(active_incident_id)]
                if active_incident_id is not None and not df.empty
                else pd.DataFrame()
            )
            if not active_matches.empty:
                st.caption(
                    "NEW CASE · REFRESH DASHBOARD DATA TO ADVANCE"
                )
                active_incident = active_matches.iloc[0]
                incident_type = str(active_incident["incident_type"])
                address = str(active_incident["address"])
                latitude = float(active_incident["latitude"])
                longitude = float(active_incident["longitude"])
                nearby_stations = nearest_training_stations(
                    latitude,
                    longitude,
                    police_stations,
                    max_distance_km=35,
                )
                with st.container(border=True):
                    st.markdown(
                        incident_hud_html(active_incident, is_active=True),
                        unsafe_allow_html=True,
                    )
                    st.button(
                        (
                            "Clear map selection"
                            if st.session_state.get("map_focus_event_id")
                            == active_incident_id
                            else "Show incident and nearby stations"
                        ),
                        key=f"show-incident-location-{active_incident_id}",
                        use_container_width=True,
                        on_click=toggle_incident_map_focus,
                        args=(active_incident_id,),
                    )
                    if not nearby_stations:
                        st.caption("Nearby police stations unavailable")
                        st.button(
                            "Send alert message",
                            key=f"send-incident-alert-{active_incident_id}",
                            use_container_width=True,
                            disabled=True,
                        )
                    else:
                        st.caption("Nearby police stations:")
                        for nearby_station, station_distance in nearby_stations:
                            st.markdown(
                                f"- {html.escape(str(nearby_station['name']))} · "
                                f"{station_distance:.1f} km"
                            )
                        station_choices = {
                            str(station["station_id"]): (station, station_distance)
                            for station, station_distance in nearby_stations
                        }
                        selected_station_id = st.selectbox(
                            "Send alert to",
                            list(station_choices),
                            format_func=lambda station_id: (
                                f"{station_choices[station_id][0]['name']} · "
                                f"{station_choices[station_id][1]:.1f} km"
                            ),
                            key=f"incident-station-choice-{active_incident_id}",
                        )
                        station, distance_km = station_choices[selected_station_id]
                        st.button(
                            "Send alert message",
                            key=f"send-incident-alert-{active_incident_id}",
                            use_container_width=True,
                            on_click=record_incident_station_alert,
                            args=(
                                active_incident_id,
                                incident_type,
                                address,
                                latitude,
                                longitude,
                                station["name"],
                                distance_km,
                            ),
                        )
            elif active_incident_id is None:
                st.caption("No incidents to display.")
            else:
                st.caption("Waiting for the next incident.")

            previous_incidents = st.session_state.get(
                "previous_action_incidents", []
            )
            if previous_incidents:
                st.markdown(
                    f"**Previous cases (queued) · {len(previous_incidents)}**"
                )
                for previous_incident in reversed(previous_incidents):
                    previous_id = str(previous_incident["event_id"])
                    previous_latitude = float(previous_incident["latitude"])
                    previous_longitude = float(previous_incident["longitude"])
                    with st.container(border=True):
                        st.markdown(
                            incident_hud_html(previous_incident),
                            unsafe_allow_html=True,
                        )
                        st.button(
                            (
                                "Clear map selection"
                                if st.session_state.get("map_focus_event_id")
                                == previous_id
                                else "Show incident and nearby stations"
                            ),
                            key=f"show-previous-location-{previous_id}",
                            use_container_width=True,
                            on_click=toggle_incident_map_focus,
                            args=(previous_id,),
                        )
                        previous_stations = nearest_training_stations(
                            previous_latitude,
                            previous_longitude,
                            police_stations,
                            max_distance_km=35,
                        )
                        if not previous_stations:
                            st.caption("Nearby police stations unavailable")
                            st.button(
                                "Send alert message",
                                key=f"send-previous-alert-{previous_id}",
                                use_container_width=True,
                                disabled=True,
                            )
                        else:
                            st.caption("Nearby police stations:")
                            for nearby_station, station_distance in previous_stations:
                                st.markdown(
                                    f"- {html.escape(str(nearby_station['name']))} · "
                                    f"{station_distance:.1f} km"
                                )
                            previous_station_choices = {
                                str(station["station_id"]): (
                                    station,
                                    station_distance,
                                )
                                for station, station_distance in previous_stations
                            }
                            selected_previous_station_id = st.selectbox(
                                "Send alert to",
                                list(previous_station_choices),
                                format_func=lambda station_id: (
                                    f"{previous_station_choices[station_id][0]['name']} · "
                                    f"{previous_station_choices[station_id][1]:.1f} km"
                                ),
                                key=f"previous-station-choice-{previous_id}",
                            )
                            previous_station, previous_distance = (
                                previous_station_choices[
                                    selected_previous_station_id
                                ]
                            )
                            st.button(
                                "Send alert message",
                                key=f"send-previous-alert-{previous_id}",
                                use_container_width=True,
                                on_click=record_incident_station_alert,
                                args=(
                                    previous_id,
                                    str(previous_incident["incident_type"]),
                                    str(previous_incident["address"]),
                                    previous_latitude,
                                    previous_longitude,
                                    previous_station["name"],
                                    previous_distance,
                                ),
                            )

            route_incident_records = {}
            if not active_matches.empty:
                route_incident_records[active_incident_id] = (
                    active_matches.iloc[0].to_dict()
                )
            for previous_incident in previous_incidents:
                route_incident_records[str(previous_incident["event_id"])] = (
                    previous_incident
                )
            if not route_incident_records and not map_df.empty:
                route_incident_records.update(
                    {
                        str(incident["event_id"]): incident
                        for incident in map_df.head(50).to_dict(orient="records")
                    }
                )
            if route_incident_records:
                st.markdown('<div class="radar-panel"><h3>Station Route Planner</h3></div>', unsafe_allow_html=True)
                route_incident_ids = list(route_incident_records)
                route_incident_key = "route-planner-incident"
                if st.session_state.get(route_incident_key) not in route_incident_records:
                    st.session_state[route_incident_key] = route_incident_ids[0]
                selected_route_incident_id = st.selectbox(
                    "Incident",
                    route_incident_ids,
                    format_func=lambda event_id: (
                        f"{route_incident_records[event_id]['incident_type']} · "
                        f"{route_incident_records[event_id]['address']}"
                    ),
                    key=route_incident_key,
                )
                selected_route_incident = route_incident_records[
                    selected_route_incident_id
                ]
                route_stations = nearest_training_stations(
                    float(selected_route_incident["latitude"]),
                    float(selected_route_incident["longitude"]),
                    police_stations,
                    max_distance_km=35,
                )
                if not route_stations:
                    st.caption("No nearby stations are available for this incident.")
                else:
                    route_station_choices = {
                        str(station["station_id"]): (station, distance_km)
                        for station, distance_km in route_stations
                    }
                    route_station_key = (
                        f"route-station-{selected_route_incident_id}"
                    )
                    if st.session_state.get(route_station_key) not in route_station_choices:
                        st.session_state[route_station_key] = next(
                            iter(route_station_choices)
                        )
                    selected_route_station_id = st.selectbox(
                            "From station",
                        list(route_station_choices),
                        format_func=lambda station_id: (
                            f"{route_station_choices[station_id][0]['name']} · "
                                f"{route_station_choices[station_id][1]:.1f} km from incident"
                        ),
                        key=route_station_key,
                    )
                    comparison_station_choices = {
                        station_id: choice
                        for station_id, choice in route_station_choices.items()
                        if station_id != selected_route_station_id
                    }
                    selected_comparison_station_id = None
                    if comparison_station_choices:
                        comparison_key = (
                            f"route-compare-{selected_route_incident_id}-"
                            f"{selected_route_station_id}"
                        )
                        if st.session_state.get(comparison_key) not in comparison_station_choices:
                            st.session_state[comparison_key] = next(
                                iter(comparison_station_choices)
                            )
                        selected_comparison_station_id = st.selectbox(
                                "Compare station",
                            list(comparison_station_choices),
                            format_func=lambda station_id: (
                                f"{comparison_station_choices[station_id][0]['name']} · "
                                    f"{comparison_station_choices[station_id][1]:.1f} km from incident"
                            ),
                            key=comparison_key,
                        )
                        route_coordinates_shared = st.checkbox(
                            "Share exact coordinates with the configured OSRM router",
                            key="route-sharing-consent",
                        )
                    st.caption(
                            f"Router: {ROUTING_SERVICE_URL}. Road distance and ETA are "
                            "estimates without live traffic. "
                        "Enabling this sends exact incident and station coordinates "
                        "to the routing service. It does not dispatch anyone."
                    )
                    if route_coordinates_shared:
                        primary_route = road_routes.get(selected_route_station_id)
                        if primary_route is not None:
                            st.markdown(
                                    f"**Route from {html.escape(route_station_choices[selected_route_station_id][0]['name'])} to incident**"
                            )
                            route_metrics = st.columns(2)
                            route_metrics[0].metric(
                                "Road distance", f"{primary_route['distance_km']:.1f} km"
                            )
                            route_metrics[1].metric(
                                "Estimated ETA",
                                f"{max(1, round(primary_route['duration_minutes']))} min",
                            )
                        else:
                            st.warning(
                                route_errors.get(
                                    selected_route_station_id,
                                    "Road route unavailable. Check the routing service.",
                                )
                            )
                        if selected_comparison_station_id is not None:
                            comparison_route = road_routes.get(
                                selected_comparison_station_id
                            )
                            if comparison_route is not None:
                                st.markdown(
                                        f"**Compare from {html.escape(comparison_station_choices[selected_comparison_station_id][0]['name'])} to incident**"
                                )
                                comparison_metrics = st.columns(2)
                                comparison_metrics[0].metric(
                                    "Road distance",
                                    f"{comparison_route['distance_km']:.1f} km",
                                )
                                comparison_metrics[1].metric(
                                    "Estimated ETA",
                                    f"{max(1, round(comparison_route['duration_minutes']))} min",
                                )
                            else:
                                st.caption(
                                    route_errors.get(
                                        selected_comparison_station_id,
                                        "Comparison road route unavailable.",
                                    )
                                )
                    else:
                        st.info("Enable coordinate sharing to load road routes and ETA.")
                    st.button(
                        "Focus selected incident on map",
                        key=f"focus-route-{selected_route_incident_id}",
                        use_container_width=True,
                        on_click=focus_incident_on_map,
                        args=(selected_route_incident_id,),
                    )

if dashboard_page == "↗  Crime Analysis":
    render_crime_trends_dashboard()
elif dashboard_page == "▤  Track Complaint":
    with st.container(border=True):
        render_complaint_tracking()
elif dashboard_page == "◈  Related crime incidents":
    render_related_incidents()
elif dashboard_page == "◈  Crime risk zones":
    with st.container(border=True):
        render_crime_risk_zones()
else:
    render_live_dashboard()
