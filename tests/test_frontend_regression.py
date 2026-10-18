from datetime import datetime
from types import SimpleNamespace
from unittest import mock

import frontend.app as dashboard


def test_render_complaint_tracking_handles_demo_records():
    with (
        mock.patch.object(dashboard.st, "markdown"),
        mock.patch.object(dashboard.st, "info"),
        mock.patch.object(dashboard.st, "text_input", return_value=""),
        mock.patch.object(
            dashboard.st,
            "selectbox",
            side_effect=["", "All statuses", "DEMO-CASE-100"],
        ),
        mock.patch.object(dashboard.st, "caption"),
        mock.patch.object(dashboard.st, "dataframe"),
        mock.patch.object(
            dashboard.st,
            "columns",
            return_value=[
                SimpleNamespace(markdown=mock.Mock()),
                SimpleNamespace(markdown=mock.Mock()),
            ],
        ),
        mock.patch.object(
            dashboard.st,
            "session_state",
            {"dashboard_incidents_for_tracking": [{
                "status": "SIMULATED DEMO EVENT",
                "event_id": "DEMO-CASE-100",
                "incident_type": "THEFT",
                "timestamp": datetime(2026, 10, 17, 12, 0),
                "address": "Chennai",
                "report_details": "Demo report details",
            }]},
            create=True,
        ),
    ):
        dashboard.render_complaint_tracking()
