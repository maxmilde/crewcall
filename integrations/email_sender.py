"""Send email from the work Gmail (same GMAIL_ADDRESS / GMAIL_APP_PASSWORD as the inbox).

Used for new recruits' work contracts. Without the Gmail settings it prints instead.
"""
import os
import smtplib
from email.message import EmailMessage

from dotenv import load_dotenv

load_dotenv()


def send_email(to: str, subject: str, body: str, attachments: dict[str, str] | None = None) -> None:
    """attachments: file name -> text content (e.g. {"work_contract.txt": contract})."""
    address, password = os.getenv("GMAIL_ADDRESS"), os.getenv("GMAIL_APP_PASSWORD")
    if not (address and password and to):
        print(f"\n[email not sent: no Gmail settings or no address] to {to}: {subject}\n{body[:300]}")
        return
    msg = EmailMessage()
    msg["From"], msg["To"], msg["Subject"] = address, to, subject
    msg.set_content(body)
    for name, content in (attachments or {}).items():
        msg.add_attachment(content.encode("utf-8"), maintype="text", subtype="plain", filename=name)
    with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=30) as smtp:
        smtp.login(address, password)
        smtp.send_message(msg)
    print(f"[email] sent to {to}: {subject}")
