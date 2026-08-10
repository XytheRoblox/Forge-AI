"""MCP server for the Google APIs an agent can be authorised against.

Runs as a stdio subprocess inside the agent's own container, so it sees that
agent's credentials and nobody else's. It is handed a REFRESH token rather
than an access token: access tokens last about an hour and an agent is
expected to outlive that, so exchanging one here — and re-exchanging it when
it expires — is the only way a long-lived agent keeps working without a human
re-authorising every hour.

Which tools appear is decided by GOOGLE_CAPABILITIES, so an agent that
attached only Calendar doesn't get Classroom tools it has no scope for. That
matters beyond tidiness: a model offered a tool it can't legally call will try
it, and spend a turn discovering the failure.
"""

import json
import os
import time
from typing import Optional

import httpx
from mcp.server.fastmcp import FastMCP

TOKEN_ENDPOINT = "https://oauth2.googleapis.com/token"

CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID", "")
CLIENT_SECRET = os.environ.get("GOOGLE_CLIENT_SECRET", "")
REFRESH_TOKEN = os.environ.get("GOOGLE_REFRESH_TOKEN", "")
ENABLED = {c.strip() for c in os.environ.get("GOOGLE_CAPABILITIES", "").split(",") if c.strip()}

mcp = FastMCP("Google")

_token: Optional[str] = None
_expires_at = 0.0


def _access_token() -> str:
    """A valid access token, refreshed when the cached one is close to expiry.

    Refreshed 60s early so a token can't expire between this check and the
    request that uses it."""
    global _token, _expires_at
    if _token and time.time() < _expires_at - 60:
        return _token
    if not (CLIENT_ID and CLIENT_SECRET and REFRESH_TOKEN):
        raise RuntimeError(
            "This agent has no connected Google account. Connect one on the agent's Review step."
        )
    response = httpx.post(
        TOKEN_ENDPOINT,
        data={
            "client_id": CLIENT_ID,
            "client_secret": CLIENT_SECRET,
            "refresh_token": REFRESH_TOKEN,
            "grant_type": "refresh_token",
        },
        timeout=30.0,
    )
    if response.status_code != 200:
        raise RuntimeError(
            "Google refused to refresh this connection — it may have been revoked. "
            "Reconnect the account on the agent's Review step."
        )
    payload = response.json()
    _token = payload["access_token"]
    _expires_at = time.time() + float(payload.get("expires_in", 3600))
    return _token


def _call(method: str, url: str, **kwargs) -> dict:
    """One Google API call, with errors turned into text a model can act on.

    A raw Google error body is mostly boilerplate; the reason and message are
    the parts that tell a model whether to fix its arguments, ask the user to
    reconnect, or give up."""
    try:
        response = httpx.request(
            method,
            url,
            headers={"Authorization": f"Bearer {_access_token()}"},
            timeout=30.0,
            **kwargs,
        )
    except httpx.HTTPError as exc:
        raise RuntimeError(f"Could not reach Google: {exc}")

    if response.status_code == 403:
        raise RuntimeError(
            "Google denied this request. The agent's authorisation may not include the "
            "necessary scope — reconnect the account after attaching this capability."
        )
    if response.status_code >= 400:
        try:
            error = response.json().get("error", {})
            detail = error.get("message") or json.dumps(error)[:200]
        except ValueError:
            detail = response.text[:200]
        raise RuntimeError(f"Google API error ({response.status_code}): {detail}")
    return response.json() if response.content else {}


# --------------------------------------------------------------- Calendar

if "calendar" in ENABLED:

    @mcp.tool()
    def list_calendar_events(time_min: str = "", time_max: str = "", max_results: int = 10) -> str:
        """List upcoming events from the user's primary Google Calendar.

        time_min/time_max are RFC3339 timestamps (e.g. 2026-08-11T00:00:00Z).
        Omit time_min to list from now."""
        params = {
            "maxResults": max(1, min(max_results, 50)),
            "singleEvents": "true",
            "orderBy": "startTime",
            "timeMin": time_min or time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }
        if time_max:
            params["timeMax"] = time_max
        data = _call(
            "GET",
            "https://www.googleapis.com/calendar/v3/calendars/primary/events",
            params=params,
        )
        items = data.get("items", [])
        if not items:
            return "No events found in that range."
        lines = []
        for event in items:
            start = event.get("start", {})
            when = start.get("dateTime") or start.get("date") or "(no start)"
            lines.append(f"- {when} — {event.get('summary', '(untitled)')} [id: {event.get('id')}]")
        return "\n".join(lines)

    @mcp.tool()
    def create_calendar_event(
        summary: str, start: str, end: str, description: str = "", location: str = ""
    ) -> str:
        """Create an event on the user's primary Google Calendar.

        start/end are RFC3339 timestamps with a timezone offset, e.g.
        2026-08-12T15:00:00-05:00."""
        body = {
            "summary": summary,
            "start": {"dateTime": start},
            "end": {"dateTime": end},
        }
        if description:
            body["description"] = description
        if location:
            body["location"] = location
        data = _call(
            "POST",
            "https://www.googleapis.com/calendar/v3/calendars/primary/events",
            json=body,
        )
        return f"Created '{data.get('summary')}' — {data.get('htmlLink', 'no link returned')}"


# -------------------------------------------------------------- Classroom

if "google_classroom" in ENABLED:

    @mcp.tool()
    def list_courses(max_results: int = 20) -> str:
        """List the Google Classroom courses this user is enrolled in or teaches."""
        data = _call(
            "GET",
            "https://classroom.googleapis.com/v1/courses",
            params={"pageSize": max(1, min(max_results, 50)), "courseStates": "ACTIVE"},
        )
        courses = data.get("courses", [])
        if not courses:
            return "No active Classroom courses found for this account."
        return "\n".join(
            f"- {c.get('name')} [id: {c.get('id')}]"
            + (f" — {c['section']}" if c.get("section") else "")
            for c in courses
        )

    @mcp.tool()
    def list_coursework(course_id: str, max_results: int = 20) -> str:
        """List assignments for a Classroom course, with due dates.

        Use list_courses first to get a course_id."""
        data = _call(
            "GET",
            f"https://classroom.googleapis.com/v1/courses/{course_id}/courseWork",
            params={"pageSize": max(1, min(max_results, 50))},
        )
        work = data.get("courseWork", [])
        if not work:
            return "No coursework found for that course."
        lines = []
        for item in work:
            due = item.get("dueDate")
            when = (
                f"{due['year']}-{due['month']:02d}-{due['day']:02d}" if due else "no due date"
            )
            lines.append(f"- {item.get('title')} (due {when}) [id: {item.get('id')}]")
        return "\n".join(lines)


# ------------------------------------------------------------------ Docs

if "google_docs" in ENABLED:

    @mcp.tool()
    def create_doc(title: str, text: str = "") -> str:
        """Create a Google Doc, optionally with initial body text."""
        doc = _call("POST", "https://docs.googleapis.com/v1/documents", json={"title": title})
        doc_id = doc.get("documentId")
        if text:
            _call(
                "POST",
                f"https://docs.googleapis.com/v1/documents/{doc_id}:batchUpdate",
                json={"requests": [{"insertText": {"location": {"index": 1}, "text": text}}]},
            )
        return f"Created '{title}' — https://docs.google.com/document/d/{doc_id}/edit"

    @mcp.tool()
    def read_doc(document_id: str) -> str:
        """Read the text content of a Google Doc by its document id."""
        doc = _call("GET", f"https://docs.googleapis.com/v1/documents/{document_id}")
        chunks = []
        for element in doc.get("body", {}).get("content", []):
            for run in element.get("paragraph", {}).get("elements", []):
                chunk = run.get("textRun", {}).get("content")
                if chunk:
                    chunks.append(chunk)
        return "".join(chunks).strip() or "(this document is empty)"


# ----------------------------------------------------------------- Sheets

if "google_sheets" in ENABLED:

    @mcp.tool()
    def read_sheet(spreadsheet_id: str, range_a1: str = "A1:Z50") -> str:
        """Read a range of cells from a Google Sheet, e.g. range_a1='Sheet1!A1:D20'."""
        data = _call(
            "GET",
            f"https://sheets.googleapis.com/v4/spreadsheets/{spreadsheet_id}/values/{range_a1}",
        )
        rows = data.get("values", [])
        if not rows:
            return "That range is empty."
        return "\n".join("\t".join(str(cell) for cell in row) for row in rows)

    @mcp.tool()
    def append_sheet_row(spreadsheet_id: str, values: list[str], range_a1: str = "A1") -> str:
        """Append one row of values to a Google Sheet."""
        _call(
            "POST",
            f"https://sheets.googleapis.com/v4/spreadsheets/{spreadsheet_id}/values/{range_a1}:append",
            params={"valueInputOption": "USER_ENTERED"},
            json={"values": [values]},
        )
        return f"Appended a row of {len(values)} values."


# ------------------------------------------------------------------ Drive

if "google_drive" in ENABLED:

    @mcp.tool()
    def find_drive_files(query: str = "", max_results: int = 10) -> str:
        """Find files the agent can access in Google Drive.

        Only files this agent created, or that the user explicitly opened with
        it, are visible — the agent holds the drive.file scope, not full Drive
        access."""
        params = {
            "pageSize": max(1, min(max_results, 50)),
            "fields": "files(id,name,mimeType,webViewLink)",
        }
        if query:
            params["q"] = f"name contains '{query}'"
        data = _call("GET", "https://www.googleapis.com/drive/v3/files", params=params)
        files = data.get("files", [])
        if not files:
            return "No matching files this agent has access to."
        return "\n".join(f"- {f['name']} [{f['id']}] {f.get('webViewLink', '')}" for f in files)


if __name__ == "__main__":
    mcp.run(transport="stdio")
