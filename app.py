from collections import defaultdict, deque
from html import escape
from email.utils import parseaddr
from ipaddress import ip_address
from threading import Lock
from time import monotonic
from werkzeug.exceptions import RequestEntityTooLarge

from flask import Flask, abort, jsonify, redirect, request, send_from_directory
from dotenv import load_dotenv
import os
import re
from urllib.parse import urlparse

import requests
from werkzeug.middleware.proxy_fix import ProxyFix


load_dotenv()

app = Flask(__name__, template_folder="templates", static_folder="static")
app.config["MAX_CONTENT_LENGTH"] = 64 * 1024
try:
    trusted_proxy_count = int(os.getenv("TRUSTED_PROXY_COUNT", "0"))
except ValueError as error:
    raise RuntimeError("TRUSTED_PROXY_COUNT must be a non-negative integer.") from error
if trusted_proxy_count < 0:
    raise RuntimeError("TRUSTED_PROXY_COUNT must be a non-negative integer.")
if trusted_proxy_count:
    app.wsgi_app = ProxyFix(
        app.wsgi_app,
        x_for=trusted_proxy_count,
        x_proto=trusted_proxy_count,
    )

SITE_ROUTE_DIRS = {
    "about",
    "alt",
    "bb",
    "comm",
    "contact",
    "faq",
    "blog",
    "mdf",
    "mr",
    "pack",
    "plywood",
    "products",
    "timnlam",
}

ARTICLE_ROUTE_FILES = {
    "blog/difference-between-bwp-and-bwr-plywood": "blog/difference-between-bwp-and-bwr-plywood/index.html",
    "blog/mr-vs-bwr-vs-bwp-plywood": "blog/mr-vs-bwr-vs-bwp-plywood/index.html",
    "blog/best-plywood-for-kitchens-wardrobes-furniture": "blog/best-plywood-for-kitchens-wardrobes-furniture/index.html",
    "blog/plywood-thickness-and-sheet-size-guide": "blog/plywood-thickness-and-sheet-size-guide/index.html",
    "blog/plywood-vs-mdf-vs-blockboard": "blog/plywood-vs-mdf-vs-blockboard/index.html",
    "blog/contractor-checklist-ordering-plywood": "blog/contractor-checklist-ordering-plywood/index.html",
    "blog/retailers-explain-plywood-grades": "blog/retailers-explain-plywood-grades/index.html",
    "blog/interior-material-planning-ahmedabad": "blog/interior-material-planning-ahmedabad/index.html",
}

ROOT_STATIC_FILES = {
    ".nojekyll",
    "CNAME",
    "android-chrome-192x192.png",
    "android-chrome-512x512.png",
    "apple-touch-icon.png",
    "favicon-16x16.png",
    "favicon-32x32.png",
    "favicon.ico",
    "robots.txt",
    "site.webmanifest",
    "sitemap.xml",
}

ALLOWED_ORIGINS = {
    "https://shreejisalescorp.in",
    "https://www.shreejisalescorp.in",
    "https://api.shreejisalescorp.in",
    "https://priyanbhatt.github.io",
}
PRODUCT_CHOICES = {
    "Alternate Plywood",
    "Commercial Plywood",
    "Packing Grade Plywood",
    "MR Grade Plywood",
    "Blockboard & Flushdoor",
    "MDF",
    "Laminate & Timber",
}
RATE_LIMIT_WINDOW_SECONDS = 60
RATE_LIMIT_MAX_REQUESTS = 6
RATE_LIMIT_MAX_TRACKED_CLIENTS = 10_000
BREVO_EMAIL_API_URL = "https://api.brevo.com/v3/smtp/email"
DEFAULT_INQUIRY_RECEIVER_EMAIL = "shreejisalescorp.in@gmail.com"
_recent_requests = defaultdict(deque)
_rate_limit_lock = Lock()
_last_rate_limit_cleanup = monotonic()


def _client_address():
    return request.remote_addr or "unknown"


def _is_local_request():
    try:
        return ip_address(request.remote_addr or "").is_loopback
    except ValueError:
        return False


def _is_allowed_origin(origin):
    if origin in ALLOWED_ORIGINS:
        return True

    if not _is_local_request():
        return False

    parsed = urlparse(origin)
    if parsed.scheme != "http" or not parsed.hostname:
        return False

    try:
        return ip_address(parsed.hostname).is_loopback
    except ValueError:
        return parsed.hostname.lower() == "localhost"


def _is_rate_limited():
    global _last_rate_limit_cleanup

    now = monotonic()
    client = _client_address()

    with _rate_limit_lock:
        if now - _last_rate_limit_cleanup >= RATE_LIMIT_WINDOW_SECONDS:
            expired_clients = [
                address
                for address, attempts in _recent_requests.items()
                if not attempts or now - attempts[-1] >= RATE_LIMIT_WINDOW_SECONDS
            ]
            for address in expired_clients:
                del _recent_requests[address]
            _last_rate_limit_cleanup = now

        if client not in _recent_requests and len(_recent_requests) >= RATE_LIMIT_MAX_TRACKED_CLIENTS:
            client = "__rate_limit_overflow__"

        attempts = _recent_requests[client]
        while attempts and now - attempts[0] >= RATE_LIMIT_WINDOW_SECONDS:
            attempts.popleft()

        if len(attempts) >= RATE_LIMIT_MAX_REQUESTS:
            return True

        attempts.append(now)

    return False


def _form_value(field_name, maximum_length, minimum_length=1, allow_line_breaks=False):
    value = request.form.get(field_name, "").strip()
    if len(value) < minimum_length or len(value) > maximum_length:
        raise ValueError(f"Please provide a valid {field_name}.")
    forbidden_controls = r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]"
    if not allow_line_breaks:
        forbidden_controls = r"[\x00-\x1f\x7f]"
    if re.search(forbidden_controls, value):
        raise ValueError(f"Please provide a valid {field_name}.")
    return value


def _valid_email(value):
    _, address = parseaddr(value)
    return bool(re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", address)) and address == value


def _send_brevo_email(
    api_key,
    sender_email,
    sender_name,
    recipient_email,
    subject,
    body,
    reply_to=None,
    html_body=None,
):
    payload = {
        "sender": {"email": sender_email, "name": sender_name},
        "to": [{"email": recipient_email}],
        "subject": subject,
        "textContent": body,
    }
    if html_body:
        payload["htmlContent"] = html_body
    if reply_to:
        payload["replyTo"] = reply_to

    response = requests.post(
        BREVO_EMAIL_API_URL,
        headers={"accept": "application/json", "api-key": api_key, "content-type": "application/json"},
        json=payload,
        timeout=10,
    )
    if not response.ok:
        app.logger.error("Brevo email delivery failed with HTTP status %s", response.status_code)
        response.raise_for_status()


def _build_inquiry_email_html(name, email, phone, city, products, message):
    safe_name = escape(name)
    safe_email = escape(email)
    safe_phone = escape(phone)
    safe_city = escape(city)
    safe_products = escape(products)
    safe_message = escape(message).replace("\n", "<br>")

    return f"""\
<!doctype html>
<html lang="en">
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"></head>
<body style="margin:0;padding:0;background-color:#eee9df;color:#29251f;font-family:Arial,Helvetica,sans-serif;">
  <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" style="background-color:#eee9df;">
    <tr><td align="center" style="padding:32px 14px;">
      <table role="presentation" width="600" cellspacing="0" cellpadding="0" border="0" style="width:100%;max-width:600px;background-color:#fffdf8;">
        <tr><td style="padding:26px 32px;background-color:#542c22;color:#fff8ec;">
          <p style="margin:0;font-size:11px;letter-spacing:2px;text-transform:uppercase;color:#e7cda6;">Shreeji Sales Corporation</p>
          <p style="margin:28px 0 7px;font-size:12px;letter-spacing:1.5px;text-transform:uppercase;color:#e7cda6;">A new material brief</p>
          <h1 style="margin:0;font-family:Georgia,'Times New Roman',serif;font-size:32px;line-height:1.2;font-weight:normal;">{safe_name} has a project in mind.</h1>
          <p style="margin:12px 0 0;font-size:14px;line-height:1.6;color:#f3e7d5;">A few details to help you shape the right recommendation.</p>
        </td></tr>
        <tr><td style="padding:28px 32px 8px;">
          <p style="margin:0 0 16px;font-size:11px;letter-spacing:1.5px;text-transform:uppercase;color:#8c6b4f;">The material shortlist</p>
          <p style="margin:0;padding:16px 18px;border-left:3px solid #a87349;background-color:#f5f0e7;font-family:Georgia,'Times New Roman',serif;font-size:19px;line-height:1.55;color:#392c24;">{safe_products}</p>
        </td></tr>
        <tr><td style="padding:16px 32px 8px;">
          <p style="margin:0 0 12px;font-size:11px;letter-spacing:1.5px;text-transform:uppercase;color:#8c6b4f;">Project notes</p>
          <div style="font-size:15px;line-height:1.8;color:#403b34;">{safe_message}</div>
        </td></tr>
        <tr><td style="padding:20px 32px 30px;">
          <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" style="border-top:1px solid #e5ddd0;">
            <tr><td style="padding:14px 0 5px;font-size:10px;letter-spacing:1.3px;text-transform:uppercase;color:#8c6b4f;">From</td></tr>
            <tr><td style="padding:0 0 12px;font-size:14px;line-height:1.6;color:#403b34;">{safe_name} &nbsp;·&nbsp; {safe_city}</td></tr>
            <tr><td style="padding:0 0 5px;font-size:10px;letter-spacing:1.3px;text-transform:uppercase;color:#8c6b4f;">Continue the conversation</td></tr>
            <tr><td style="font-size:14px;line-height:1.8;color:#403b34;"><a href="mailto:{safe_email}" style="color:#71432f;">{safe_email}</a><br>{safe_phone}</td></tr>
          </table>
        </td></tr>
        <tr><td style="padding:15px 32px;background-color:#f5f0e7;font-size:11px;line-height:1.6;color:#766d62;">
          Made for better-built spaces. Reply directly to this email to reach {safe_name}.
        </td></tr>
      </table>
    </td></tr>
  </table>
</body>
</html>"""


def _build_confirmation_email_html(name):
    safe_name = escape(name)
    return f"""\
<!doctype html>
<html lang="en">
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"></head>
<body style="margin:0;padding:0;background-color:#eee9df;color:#29251f;font-family:Arial,Helvetica,sans-serif;">
  <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" style="background-color:#eee9df;">
    <tr><td align="center" style="padding:32px 14px;">
      <table role="presentation" width="560" cellspacing="0" cellpadding="0" border="0" style="width:100%;max-width:560px;background-color:#fffdf8;">
        <tr><td style="padding:28px 32px;background-color:#542c22;color:#fff8ec;">
          <p style="margin:0;font-size:11px;letter-spacing:2px;text-transform:uppercase;color:#e7cda6;">Shreeji Sales Corporation</p>
          <p style="margin:36px 0 8px;font-size:12px;letter-spacing:1.5px;text-transform:uppercase;color:#e7cda6;">Your project, in motion</p>
          <h1 style="margin:0;font-family:Georgia,'Times New Roman',serif;font-size:32px;line-height:1.2;font-weight:normal;">Your brief is on our workbench.</h1>
        </td></tr>
        <tr><td style="padding:28px 32px 34px;font-size:15px;line-height:1.8;color:#403b34;">
          <p style="margin:0 0 14px;">Hello {safe_name},</p>
          <p style="margin:0 0 14px;">Your material and project notes have reached our team. We’ll review the details and follow up with you directly.</p>
          <p style="margin:0;font-family:Georgia,'Times New Roman',serif;font-size:18px;color:#71432f;">Until then, keep the good ideas coming.</p>
        </td></tr>
        <tr><td style="padding:15px 32px;background-color:#f5f0e7;font-size:12px;line-height:1.7;color:#766d62;">
          Need to add a detail? Reply to this email or call +91 94270 20838.
        </td></tr>
      </table>
    </td></tr>
  </table>
</body>
</html>"""


@app.after_request
def add_security_headers(response):
    origin = request.headers.get("Origin")
    if origin and _is_allowed_origin(origin):
        response.headers["Access-Control-Allow-Origin"] = origin
        response.headers["Access-Control-Allow-Methods"] = "POST, OPTIONS"
        response.headers["Access-Control-Allow-Headers"] = "Content-Type"
        response.headers["Vary"] = "Origin"

    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "SAMEORIGIN"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "camera=(), geolocation=(), microphone=()"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; "
        "base-uri 'self'; "
        "object-src 'none'; "
        "form-action 'self' https://api.shreejisalescorp.in; "
        "img-src 'self' data: https://www.google.com https://www.gstatic.com https://www.recaptcha.net; "
        "style-src 'self' https://fonts.googleapis.com https://cdnjs.cloudflare.com; "
        "font-src 'self' https://fonts.gstatic.com https://cdnjs.cloudflare.com; "
        "script-src 'self' https://www.google.com https://www.gstatic.com https://www.recaptcha.net; "
        "frame-src https://www.google.com https://www.recaptcha.net; "
        "connect-src 'self' https://api.shreejisalescorp.in https://www.google.com https://www.recaptcha.net"
    )

    if request.is_secure:
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"

    return response


@app.errorhandler(RequestEntityTooLarge)
def request_too_large(_error):
    return jsonify({"status": "error", "message": "The inquiry is too large."}), 413


@app.route("/", strict_slashes=False)
def home():
    return send_from_directory(app.root_path, "index.html")


@app.route("/healthz")
def health_check():
    return jsonify({"status": "ok"})


@app.route("/<path:page>", strict_slashes=False)
def serve_site_page(page):
    page = page.strip("/")

    if page in ROOT_STATIC_FILES:
        return send_from_directory(app.root_path, page)

    if page in ARTICLE_ROUTE_FILES:
        if not request.path.endswith("/"):
            return redirect(f"/{page}/", code=308)
        return send_from_directory(app.root_path, ARTICLE_ROUTE_FILES[page])

    if page in SITE_ROUTE_DIRS:
        if not request.path.endswith("/"):
            return redirect(f"/{page}/", code=308)
        return send_from_directory(os.path.join(app.root_path, page), "index.html")

    abort(404)


@app.route("/send_inquiry", methods=["POST", "OPTIONS"])
def send_inquiry():
    origin = request.headers.get("Origin")
    if origin and not _is_allowed_origin(origin):
        return jsonify({"status": "error", "message": "Request origin is not allowed."}), 403

    if request.method == "OPTIONS":
        return ("", 204)

    if _is_rate_limited():
        return jsonify({"status": "error", "message": "Please wait a minute before trying again."}), 429

    try:
        name = _form_value("name", 100)
        email = _form_value("email", 254)
        phone = _form_value("phone", 30)
        city = _form_value("city", 100)
        message = _form_value("message", 2000, minimum_length=5, allow_line_breaks=True)
    except ValueError as error:
        return jsonify({"status": "error", "message": str(error)}), 400

    if not _valid_email(email):
        return jsonify({"status": "error", "message": "Please provide a valid email address."}), 400

    phone_digits = re.sub(r"\D", "", phone)
    if not 7 <= len(phone_digits) <= 15:
        return jsonify({"status": "error", "message": "Please provide a valid phone number."}), 400

    selected_products = [
        product for product in request.form.getlist("product[]") if product in PRODUCT_CHOICES
    ]
    products = ", ".join(selected_products) or "Not specified"

    captcha_token = request.form.get("g-recaptcha-response", "").strip()
    captcha_secret = os.getenv("RECAPTCHA_SECRET_KEY") or os.getenv("secretkeycap")
    if _is_local_request():
        captcha_secret = os.getenv("LOCAL_RECAPTCHA_TEST_SECRET") or captcha_secret
    if not captcha_token:
        return jsonify({"status": "error", "message": "Please complete the security check."}), 400
    if not captcha_secret:
        app.logger.error("reCAPTCHA secret is not configured")
        return jsonify({"status": "error", "message": "The inquiry service is temporarily unavailable."}), 503

    try:
        verification = requests.post(
            "https://www.google.com/recaptcha/api/siteverify",
            data={
                "secret": captcha_secret,
                "response": captcha_token,
                "remoteip": _client_address(),
            },
            timeout=8,
        )
        verification.raise_for_status()
        if not verification.json().get("success"):
            return jsonify({"status": "error", "message": "Security verification failed. Please try again."}), 400
    except (requests.RequestException, ValueError):
        app.logger.exception("reCAPTCHA verification failed")
        return jsonify({"status": "error", "message": "The inquiry service is temporarily unavailable."}), 503

    brevo_api_key = os.getenv("BREVO_API_KEY")
    sender_email = os.getenv("BREVO_SENDER_EMAIL", "")
    sender_name = os.getenv("BREVO_SENDER_NAME", "Shreeji Sales Corporation")
    receiver_email = os.getenv("INQUIRY_RECEIVER_EMAIL", DEFAULT_INQUIRY_RECEIVER_EMAIL)
    if (
        not brevo_api_key
        or not _valid_email(sender_email)
        or not _valid_email(receiver_email)
    ):
        app.logger.error("Brevo email service settings are missing or invalid")
        return jsonify({"status": "error", "message": "The inquiry service is temporarily unavailable."}), 503

    inquiry_body = (
        "A new material brief has arrived.\n\n"
        f"Name: {name}\n"
        f"Email: {email}\n"
        f"Phone: {phone}\n"
        f"City: {city}\n"
        f"Products: {products}\n\n"
        f"Message:\n{message}\n"
    )
    confirmation_body = (
        f"Hello {name},\n\n"
        "Your material and project notes have reached our team. We’ll review the details and follow up with you directly.\n\n"
        "Until then, keep the good ideas coming.\n\n"
        "Need to add a detail? Reply to this email or call +91 94270 20838.\n"
        "Shreeji Sales Corporation"
    )
    inquiry_html = _build_inquiry_email_html(name, email, phone, city, products, message)
    confirmation_html = _build_confirmation_email_html(name)

    try:
        _send_brevo_email(
            brevo_api_key,
            sender_email,
            sender_name,
            receiver_email,
            "A new material brief has arrived",
            inquiry_body,
            reply_to={"email": email, "name": name},
            html_body=inquiry_html,
        )
    except requests.RequestException:
        app.logger.exception("Brevo could not deliver the inquiry notification")
        return jsonify({"status": "error", "message": "Unable to send your inquiry right now. Please call or email us."}), 502

    try:
        _send_brevo_email(
            brevo_api_key,
            sender_email,
            sender_name,
            email,
            "We received your inquiry",
            confirmation_body,
            html_body=confirmation_html,
        )
    except requests.RequestException:
        app.logger.exception("Brevo could not deliver the customer confirmation")
        return jsonify({
            "status": "success",
            "message": "Your inquiry reached our team, but we could not send a confirmation email. We will contact you shortly.",
        })

    return jsonify({"status": "success", "message": "Thank you. Your inquiry has been sent."})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "5001")), debug=False)
