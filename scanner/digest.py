"""Email digest of what changed in the last scan.

Sends only when something actually changed -- a daily "nothing new" email
trains you to ignore the whole channel, which defeats the point.

Configured entirely through environment variables so no credentials ever land
in the repo. In GitHub Actions these come from repository secrets:

    SMTP_HOST      e.g. smtp.gmail.com
    SMTP_PORT      e.g. 587
    SMTP_USER      the sending account
    SMTP_PASSWORD  an app password, NOT your account password
    DIGEST_TO      where to send it (defaults to SMTP_USER)
"""

import html
import json
import os
import smtplib
import sys
from email.message import EmailMessage

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DIGEST_PATH = os.path.join(ROOT, "data", "last_digest.json")

REGION_LABEL = {"uk": "UK", "china": "China"}


def load_digest(path=DIGEST_PATH):
    if not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def render(payload):
    """Return (subject, text_body, html_body) or None if nothing worth sending."""
    new_items = payload.get("new") or []
    errors = payload.get("errors") or []

    if not new_items and not errors:
        return None

    if new_items:
        subject = f"{len(new_items)} new internship listing(s)"
    else:
        subject = f"Scan problem: {len(errors)} firm(s) failed"

    text_lines = []
    html_parts = [
        "<div style=\"font-family:-apple-system,Segoe UI,Roboto,sans-serif;"
        "font-size:14px;color:#16202b;\">"
    ]

    if new_items:
        by_region = {}
        for item in new_items:
            by_region.setdefault(item.get("region", "other"), []).append(item)

        for region in sorted(by_region):
            label = REGION_LABEL.get(region, region.title())
            text_lines.append(f"\n{label}")
            text_lines.append("-" * len(label))
            html_parts.append(
                f"<h2 style=\"font-size:15px;margin:18px 0 8px;\">{html.escape(label)}</h2>"
            )

            for item in sorted(by_region[region], key=lambda i: (i["firm"], i["title"])):
                text_lines.append(f"  {item['firm']} - {item['title']}")
                text_lines.append(f"    {item.get('location', '')}")
                if item.get("url"):
                    text_lines.append(f"    {item['url']}")

                title = html.escape(item["title"])
                link = html.escape(item.get("url", ""))
                html_parts.append(
                    "<div style=\"margin:0 0 12px;padding:10px 12px;border:1px solid #dde3ea;"
                    "border-radius:8px;\">"
                    f"<div style=\"font-weight:700;\">{html.escape(item['firm'])}</div>"
                    f"<div style=\"margin:2px 0;\">"
                    + (f"<a href=\"{link}\">{title}</a>" if link else title)
                    + "</div>"
                    f"<div style=\"color:#5b6b7c;font-size:12.5px;\">"
                    f"{html.escape(item.get('location', ''))}</div>"
                    "</div>"
                )

    if errors:
        text_lines.append("\nFirms that failed to scan:")
        html_parts.append(
            "<h2 style=\"font-size:15px;margin:18px 0 8px;\">Failed to scan</h2><ul>"
        )
        for error in errors:
            text_lines.append(f"  {error['firm']}: {error['error']}")
            html_parts.append(
                f"<li>{html.escape(error['firm'])}: "
                f"{html.escape(str(error['error']))}</li>"
            )
        html_parts.append("</ul>")

    html_parts.append("</div>")
    return subject, "\n".join(text_lines).strip(), "".join(html_parts)


def send(subject, text_body, html_body):
    host = os.environ.get("SMTP_HOST")
    user = os.environ.get("SMTP_USER")
    password = os.environ.get("SMTP_PASSWORD")
    port = int(os.environ.get("SMTP_PORT", "587"))
    recipient = os.environ.get("DIGEST_TO") or user

    if not all([host, user, password, recipient]):
        print("SMTP not configured; skipping email.", file=sys.stderr)
        return False

    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = user
    message["To"] = recipient
    message.set_content(text_body)
    message.add_alternative(html_body, subtype="html")

    try:
        with smtplib.SMTP(host, port, timeout=30) as smtp:
            smtp.starttls()
            smtp.login(user, password)
            smtp.send_message(message)
    except smtplib.SMTPAuthenticationError as exc:
        # The single most common failure. Spell out the fix rather than
        # leaving a bare 535 in the log.
        detail = exc.smtp_error
        if isinstance(detail, bytes):
            detail = detail.decode(errors="replace")
        print(
            f"SMTP authentication failed: {detail}\n"
            "  - SMTP_PASSWORD must be a Gmail *App Password* "
            "(myaccount.google.com/apppasswords), not your account password.\n"
            "  - App Passwords require 2-Step Verification to be enabled.\n"
            "  - SMTP_USER must be the same Google account that made the App Password.",
            file=sys.stderr,
        )
        return False
    except (smtplib.SMTPException, OSError) as exc:
        print(
            f"Could not send digest via {host}:{port} -- {type(exc).__name__}: {exc}",
            file=sys.stderr,
        )
        return False

    print(f"Digest sent to {recipient}")
    return True


def main():
    payload = load_digest()
    if payload is None:
        print("No digest payload; run a scan first.")
        return 0

    rendered = render(payload)
    if rendered is None:
        print("Nothing new; no email sent.")
        return 0

    subject, text_body, html_body = rendered
    if "--print" in sys.argv:
        print(f"Subject: {subject}\n")
        print(text_body)
        return 0

    # Exit non-zero on failure so the workflow run turns red and you notice --
    # the workflow is ordered so the scan results are already committed by
    # this point, so a broken email never costs you data.
    return 0 if send(subject, text_body, html_body) else 1


if __name__ == "__main__":
    sys.exit(main())
