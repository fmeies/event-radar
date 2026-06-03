from email.message import EmailMessage
from typing import Any

import aiosmtplib

from .config import settings
from .logger import get_logger

log = get_logger("email")


def _base_msg(to_email: str, subject: str) -> EmailMessage:
    msg = EmailMessage()
    msg["From"] = settings.from_email
    msg["To"] = to_email
    msg["Subject"] = subject
    return msg


async def _send(msg: EmailMessage) -> None:
    kwargs: dict[str, Any] = {
        "hostname": settings.smtp_host,
        "port": settings.smtp_port,
    }
    if settings.smtp_user:
        kwargs["username"] = settings.smtp_user
        kwargs["password"] = settings.smtp_password
    if settings.smtp_port == 465:
        kwargs["use_tls"] = True
    elif settings.smtp_port == 587:
        kwargs["start_tls"] = True
    log.debug(
        "Sending email to %s via %s:%d",
        msg["To"],
        settings.smtp_host,
        settings.smtp_port,
    )
    await aiosmtplib.send(msg, **kwargs)
    log.info("Email sent to %s: %s", msg["To"], msg["Subject"])


async def send_verification_email(to_email: str, token: str) -> None:
    verify_url = f"{settings.base_url}/verify?token={token}"
    log.info("Sending verification email to %s", to_email)
    msg = _base_msg(to_email, "Event Radar – Confirm your email address")
    msg.set_content(
        f"Hi,\n\n"
        f"Please confirm your email address by clicking the link below:\n\n"
        f"  {verify_url}\n\n"
        f"This link expires in 24 hours.\n\n"
        f"– Event Radar"
    )
    await _send(msg)


async def send_event_notification(
    to_email: str, events: list[dict], location: str
) -> None:
    log.info(
        "Sending event notification to %s (%d event(s) in %s)",
        to_email,
        len(events),
        location,
    )
    lines: list[str] = []
    for e in events:
        lines.append(f"Event:  {e.get('name', 'Unknown')}")
        lines.append(f"Date:   {e.get('date') or 'unknown'}")
        venue = e.get("venue") or ""
        city = e.get("city") or location
        lines.append(f"Venue:  {', '.join(filter(None, [venue, city]))}")
        if e.get("url"):
            lines.append(f"Link:   {e['url']}")
        lines.append("")

    msg = _base_msg(to_email, f"Event Radar – New events in {location}")
    msg.set_content(
        f"Hi,\n\n"
        f"We found {len(events)} new event(s) in {location} for you:\n\n"
        + "\n".join(lines)
        + "Enjoy!\n– Event Radar"
    )
    await _send(msg)
