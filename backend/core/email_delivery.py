"""Provider-neutral SMTP delivery for account verification and recovery."""

from email.message import EmailMessage
import logging
import smtplib
import ssl
from urllib.parse import urlencode

from core.auth_tokens import EMAIL_VERIFICATION, PASSWORD_RESET
from core.config import settings


logger = logging.getLogger(__name__)


def _message_for(purpose: str, recipient: str, raw_token: str) -> EmailMessage:
    if purpose == EMAIL_VERIFICATION:
        path = "/verify-email"
        subject = "Tax Advisor — подтвердите email / ელფოსტის დადასტურება"
        action_ru = "Подтвердить email"
        action_ka = "ელფოსტის დადასტურება"
        action_en = "Verify email"
    elif purpose == PASSWORD_RESET:
        path = "/reset-password"
        subject = "Tax Advisor — сброс пароля / პაროლის აღდგენა"
        action_ru = "Сбросить пароль"
        action_ka = "პაროლის აღდგენა"
        action_en = "Reset password"
    else:
        raise ValueError(f"unsupported email purpose: {purpose}")

    url = f"{settings.AUTH_PUBLIC_BASE_URL.rstrip('/')}{path}?{urlencode({'token': raw_token})}"
    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = settings.SMTP_FROM
    message["To"] = recipient
    message.set_content(
        "Tax Advisor\n\n"
        f"RU: {action_ru}: {url}\n"
        f"KA: {action_ka}: {url}\n"
        f"EN: {action_en}: {url}\n\n"
        "Если вы не запрашивали это действие, проигнорируйте письмо.\n"
        "თუ ეს მოქმედება არ მოგითხოვიათ, უგულებელყავით წერილი.\n"
        "If you did not request this action, ignore this email.\n"
    )
    return message


def send_auth_email(purpose: str, recipient: str, raw_token: str) -> None:
    """Send one account action email without logging its credential."""
    if not settings.EMAIL_DELIVERY_ENABLED:
        return

    message = _message_for(purpose, recipient, raw_token)
    smtp_class = smtplib.SMTP_SSL if settings.SMTP_USE_SSL else smtplib.SMTP
    try:
        with smtp_class(
            settings.SMTP_HOST,
            settings.SMTP_PORT,
            timeout=settings.SMTP_TIMEOUT_SECONDS,
        ) as client:
            if settings.SMTP_USE_TLS:
                client.starttls(context=ssl.create_default_context())
            if settings.SMTP_USER:
                password = (
                    settings.SMTP_PASSWORD.get_secret_value()
                    if settings.SMTP_PASSWORD
                    else ""
                )
                client.login(settings.SMTP_USER, password)
            client.send_message(message)
    except Exception:
        logger.exception("Account email delivery failed for purpose=%s", purpose)
