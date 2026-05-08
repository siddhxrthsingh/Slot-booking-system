"""
Email notification service — silently skips if SMTP is not configured.
Uses aiosmtplib for async delivery.
"""
import logging
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from app.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


def _smtp_enabled() -> bool:
    return bool(settings.smtp_host and settings.smtp_user)


async def _send(to: str, subject: str, html: str) -> None:
    if not _smtp_enabled():
        logger.debug("Email skipped (SMTP not configured): %s", subject)
        return
    try:
        import aiosmtplib

        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"]    = settings.smtp_from
        msg["To"]      = to
        msg.attach(MIMEText(html, "html"))

        await aiosmtplib.send(
            msg,
            hostname=settings.smtp_host,
            port=settings.smtp_port,
            username=settings.smtp_user,
            password=settings.smtp_password,
            start_tls=True,
        )
        logger.info("Email sent to %s: %s", to, subject)
    except Exception as exc:
        logger.warning("Email delivery failed: %s", exc)


async def send_booking_confirmation(
    to_email: str,
    name: str,
    sport: str,
    date: str,
    time_range: str,
    venue: str,
    campus: str,
) -> None:
    subject = f"[PESU Sports] Booking Confirmed — {sport}"
    html = f"""
    <div style="font-family:sans-serif;max-width:520px;margin:auto">
      <h2 style="color:#5a3fd4">Booking Confirmed ✅</h2>
      <p>Hi {name},</p>
      <p>Your slot has been <strong>confirmed</strong>.</p>
      <table style="border-collapse:collapse;width:100%">
        <tr><td style="padding:6px 0;color:#666">Sport</td><td><strong>{sport}</strong></td></tr>
        <tr><td style="padding:6px 0;color:#666">Date</td><td>{date}</td></tr>
        <tr><td style="padding:6px 0;color:#666">Time</td><td>{time_range}</td></tr>
        <tr><td style="padding:6px 0;color:#666">Venue</td><td>{venue}</td></tr>
        <tr><td style="padding:6px 0;color:#666">Campus</td><td>{campus}</td></tr>
      </table>
      <p style="color:#888;font-size:0.85em;margin-top:24px">
        You must cancel at least 2 hours before the slot to avoid a booking suspension.<br>
        PESU Sports Slot Booking System
      </p>
    </div>
    """
    await _send(to_email, subject, html)


async def send_booking_cancellation(
    to_email: str,
    name: str,
    sport: str,
    date: str,
    time_range: str,
    late: bool,
    banned_until: str | None,
) -> None:
    ban_note = (
        f"<p style='color:#c0392b'><strong>⚠️ Late cancellation:</strong> "
        f"Your booking access has been suspended until {banned_until}.</p>"
        if late and banned_until
        else ""
    )
    subject = f"[PESU Sports] Booking Cancelled — {sport}"
    html = f"""
    <div style="font-family:sans-serif;max-width:520px;margin:auto">
      <h2 style="color:#c0392b">Booking Cancelled</h2>
      <p>Hi {name},</p>
      <p>Your <strong>{sport}</strong> slot on <strong>{date}</strong> ({time_range}) has been cancelled.</p>
      {ban_note}
      <p style="color:#888;font-size:0.85em;margin-top:24px">PESU Sports Slot Booking System</p>
    </div>
    """
    await _send(to_email, subject, html)


async def send_ban_notification(
    to_email: str,
    name: str,
    reason: str,
    banned_until: str,
) -> None:
    subject = "[PESU Sports] Booking Access Suspended"
    html = f"""
    <div style="font-family:sans-serif;max-width:520px;margin:auto">
      <h2 style="color:#c0392b">Booking Access Suspended ⚠️</h2>
      <p>Hi {name},</p>
      <p>Your booking access has been <strong>suspended</strong>.</p>
      <p><strong>Reason:</strong> {reason}</p>
      <p><strong>Access restored:</strong> {banned_until}</p>
      <p style="color:#888;font-size:0.85em;margin-top:24px">PESU Sports Slot Booking System</p>
    </div>
    """
    await _send(to_email, subject, html)
