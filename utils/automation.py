"""Optional delivery automations for finished walkthrough PDFs."""

from __future__ import annotations

import base64
import json
import mimetypes
import os
import smtplib
import ssl
import urllib.error
import urllib.request
from dataclasses import dataclass
from email.message import EmailMessage
from pathlib import Path
from typing import Any


@dataclass
class AutomationResult:
    service: str
    ok: bool
    message: str
    url: str = ""


def _env(name: str) -> str:
    return os.getenv(name, "").strip()


def upload_to_google_drive(
    pdf_path: str | Path,
    *,
    folder_id: str,
    service_account_file: str = "",
    service_account_json: str = "",
) -> AutomationResult:
    """Upload a PDF to Google Drive using service account credentials."""
    if not folder_id:
        return AutomationResult("Google Drive", False, "Missing Google Drive folder ID.")

    service_account_file = service_account_file or _env("GOOGLE_SERVICE_ACCOUNT_FILE")
    service_account_json = service_account_json or _env("GOOGLE_SERVICE_ACCOUNT_JSON")
    if not service_account_file and not service_account_json:
        return AutomationResult(
            "Google Drive",
            False,
            "Missing service account credentials. Set GOOGLE_SERVICE_ACCOUNT_FILE or GOOGLE_SERVICE_ACCOUNT_JSON.",
        )

    try:
        from google.oauth2 import service_account
        from googleapiclient.discovery import build
        from googleapiclient.http import MediaFileUpload
    except ImportError:
        return AutomationResult(
            "Google Drive",
            False,
            "Google Drive libraries are not installed. Run `pip install -r requirements.txt`.",
        )

    try:
        scopes = ["https://www.googleapis.com/auth/drive.file"]
        if service_account_json:
            info = json.loads(service_account_json)
            credentials = service_account.Credentials.from_service_account_info(info, scopes=scopes)
        else:
            credentials = service_account.Credentials.from_service_account_file(
                service_account_file,
                scopes=scopes,
            )

        pdf = Path(pdf_path)
        media = MediaFileUpload(str(pdf), mimetype="application/pdf", resumable=False)
        metadata = {"name": pdf.name, "parents": [folder_id]}
        drive = build("drive", "v3", credentials=credentials, cache_discovery=False)
        created = (
            drive.files()
            .create(
                body=metadata,
                media_body=media,
                fields="id,name,webViewLink,webContentLink",
                supportsAllDrives=True,
            )
            .execute()
        )
        url = created.get("webViewLink") or created.get("webContentLink") or ""
        return AutomationResult("Google Drive", True, f"Uploaded {created.get('name', pdf.name)}.", url)
    except Exception as exc:
        return AutomationResult("Google Drive", False, f"Upload failed: {exc}")


def post_slack_notification(webhook_url: str, message: str) -> AutomationResult:
    """Post a completion message to Slack via incoming webhook."""
    webhook_url = webhook_url or _env("SLACK_WEBHOOK_URL")
    if not webhook_url:
        return AutomationResult("Slack", False, "Missing Slack webhook URL.")

    try:
        payload = json.dumps({"text": message}).encode("utf-8")
        request = urllib.request.Request(
            webhook_url,
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=15) as response:
            body = response.read().decode("utf-8", errors="replace")
        if 200 <= response.status < 300:
            return AutomationResult("Slack", True, "Notification sent.")
        return AutomationResult("Slack", False, f"Slack returned {response.status}: {body}")
    except urllib.error.HTTPError as exc:
        return AutomationResult("Slack", False, f"Slack returned {exc.code}: {exc.read().decode(errors='replace')}")
    except Exception as exc:
        return AutomationResult("Slack", False, f"Notification failed: {exc}")


def send_email_delivery(
    pdf_path: str | Path,
    *,
    recipients: list[str],
    subject: str,
    body: str,
    drive_url: str = "",
    attach_pdf: bool = False,
    cc: list[str] | None = None,
    smtp_host: str = "",
    smtp_port: int | None = None,
    smtp_username: str = "",
    smtp_password: str = "",
    sender: str = "",
) -> AutomationResult:
    """Send the PDF or Drive link through SMTP."""
    recipients = [recipient.strip() for recipient in recipients if recipient.strip()]
    cc = [recipient.strip() for recipient in (cc or []) if recipient.strip()]
    if not recipients:
        return AutomationResult("Email", False, "No email recipients provided.")

    smtp_host = smtp_host or _env("SMTP_HOST")
    smtp_port = smtp_port or int(_env("SMTP_PORT") or "587")
    smtp_username = smtp_username or _env("SMTP_USERNAME")
    smtp_password = smtp_password or _env("SMTP_PASSWORD")
    sender = sender or _env("SMTP_FROM") or smtp_username
    if not smtp_host or not sender:
        return AutomationResult("Email", False, "Missing SMTP_HOST and SMTP_FROM/SMTP_USERNAME.")

    message = EmailMessage()
    message["From"] = sender
    message["To"] = ", ".join(recipients)
    if cc:
        message["Cc"] = ", ".join(cc)
    message["Subject"] = subject
    message.set_content(body)

    pdf = Path(pdf_path)
    if attach_pdf and pdf.is_file():
        mime_type, _ = mimetypes.guess_type(pdf.name)
        maintype, subtype = (mime_type or "application/pdf").split("/", 1)
        message.add_attachment(
            pdf.read_bytes(),
            maintype=maintype,
            subtype=subtype,
            filename=pdf.name,
        )
    elif drive_url:
        message.set_content(f"{body}\n\nPDF: {drive_url}\n")

    try:
        context = ssl.create_default_context()
        with smtplib.SMTP(smtp_host, int(smtp_port), timeout=30) as server:
            server.starttls(context=context)
            if smtp_username and smtp_password:
                server.login(smtp_username, smtp_password)
            server.send_message(message, to_addrs=recipients + cc)
        return AutomationResult("Email", True, "Email sent.")
    except Exception as exc:
        return AutomationResult("Email", False, f"Email failed: {exc}")


def split_emails(value: str) -> list[str]:
    return [part.strip() for part in value.replace(";", ",").split(",") if part.strip()]


def build_completion_message(
    *,
    video_filename: str,
    pdf_name: str,
    screenshot_count: int,
    skipped_count: int,
    drive_url: str = "",
) -> str:
    lines = [
        f"Walkthrough PDF ready: {pdf_name}",
        f"Source video: {video_filename}",
        f"Screenshots captured: {screenshot_count}",
        f"Blank/black frames skipped: {skipped_count}",
    ]
    if drive_url:
        lines.append(f"Drive link: {drive_url}")
    return "\n".join(lines)


def encode_service_account_json(raw_json: str) -> str:
    """Normalize service account JSON pasted as plain JSON or base64."""
    raw_json = raw_json.strip()
    if not raw_json:
        return ""
    if raw_json.startswith("{"):
        return raw_json
    try:
        return base64.b64decode(raw_json).decode("utf-8")
    except Exception:
        return raw_json

