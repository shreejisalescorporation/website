from collections import defaultdict, deque
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import parseaddr
from threading import Lock
from time import monotonic
from werkzeug.exceptions import RequestEntityTooLarge

from flask import Flask, jsonify, request, send_from_directory
from dotenv import load_dotenv
import os
import re
import smtplib
import ssl

import requests


load_dotenv()

app = Flask(__name__, template_folder="templates", static_folder="static")
app.config["MAX_CONTENT_LENGTH"] = 64 * 1024

SITE_ROUTE_DIRS = {
    "about",
    "alt",
    "bb",
    "comm",
    "contact",
    "mdf",
    "mr",
    "pack",
    "plywood",
    "products",
    "timnlam",
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
_recent_requests = defaultdict(deque)
_rate_limit_lock = Lock()


def _client_address():
    forwarded_for = request.headers.get("X-Forwarded-For", "")
    return forwarded_for.split(",", 1)[0].strip() or request.remote_addr or "unknown"


def _is_rate_limited():
    now = monotonic()
    client = _client_address()

    with _rate_limit_lock:
        attempts = _recent_requests[client]
        while attempts and now - attempts[0] >= RATE_LIMIT_WINDOW_SECONDS:
            attempts.popleft()

        if len(attempts) >= RATE_LIMIT_MAX_REQUESTS:
            return True

        attempts.append(now)

    return False


def _form_value(field_name, maximum_length, minimum_length=1):
    value = request.form.get(field_name, "").strip()
    if len(value) < minimum_length or len(value) > maximum_length:
        raise ValueError(f"Please provide a valid {field_name}.")
    return value


def _valid_email(value):
    _, address = parseaddr(value)
    return bool(re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", address)) and address == value


@app.after_request
def add_security_headers(response):
    origin = request.headers.get("Origin")
    if origin in ALLOWED_ORIGINS:
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
        "img-src 'self' data: https://www.google.com; "
        "style-src 'self' https://fonts.googleapis.com https://cdnjs.cloudflare.com; "
        "font-src 'self' https://fonts.gstatic.com https://cdnjs.cloudflare.com; "
        "script-src 'self' https://www.google.com https://www.gstatic.com https://www.recaptcha.net; "
        "frame-src https://www.google.com https://www.recaptcha.net; "
        "connect-src 'self' https://api.shreejisalescorp.in"
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


@app.route("/<path:page>", strict_slashes=False)
def serve_site_page(page):
    page = page.strip("/")

    if page in ROOT_STATIC_FILES:
        return send_from_directory(app.root_path, page)

    if page in SITE_ROUTE_DIRS:
        return send_from_directory(os.path.join(app.root_path, page), "index.html")

    return send_from_directory(app.root_path, "index.html")


@app.route("/send_inquiry", methods=["POST", "OPTIONS"])
def send_inquiry():
    if request.method == "OPTIONS":
        return ("", 204)

    origin = request.headers.get("Origin")
    if origin and origin not in ALLOWED_ORIGINS:
        return jsonify({"status": "error", "message": "Request origin is not allowed."}), 403

    if _is_rate_limited():
        return jsonify({"status": "error", "message": "Please wait a minute before trying again."}), 429

    try:
        name = _form_value("name", 100)
        email = _form_value("email", 254)
        phone = _form_value("phone", 30)
        city = _form_value("city", 100)
        message = _form_value("message", 2000, minimum_length=5)
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
    captcha_secret = os.getenv("secretkeycap")
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

    sender_email = os.getenv("email")
    sender_password = os.getenv("emailpass")
    receiver_email = os.getenv("inquiry_receiver_email", sender_email)
    if not all((sender_email, sender_password, receiver_email)):
        app.logger.error("Email service credentials are not configured")
        return jsonify({"status": "error", "message": "The inquiry service is temporarily unavailable."}), 503

    inquiry_body = (
        "New website inquiry\n\n"
        f"Name: {name}\n"
        f"Email: {email}\n"
        f"Phone: {phone}\n"
        f"City: {city}\n"
        f"Products: {products}\n\n"
        f"Message:\n{message}\n"
    )
    confirmation_body = (
        f"Dear {name},\n\n"
        "Thank you for contacting Shreeji Sales Corporation. We have received your inquiry and will get back to you shortly.\n\n"
        "Best regards,\nShreeji Sales Corporation"
    )

    try:
        with smtplib.SMTP("smtp.gmail.com", 587, timeout=10) as server:
            server.ehlo()
            server.starttls(context=ssl.create_default_context())
            server.login(sender_email, sender_password)

            inquiry_message = MIMEMultipart()
            inquiry_message["From"] = sender_email
            inquiry_message["To"] = receiver_email
            inquiry_message["Subject"] = "New website inquiry"
            inquiry_message.attach(MIMEText(inquiry_body, "plain", "utf-8"))
            server.send_message(inquiry_message)

            confirmation_message = MIMEMultipart()
            confirmation_message["From"] = sender_email
            confirmation_message["To"] = email
            confirmation_message["Subject"] = "We received your inquiry"
            confirmation_message.attach(MIMEText(confirmation_body, "plain", "utf-8"))
            server.send_message(confirmation_message)
    except (OSError, smtplib.SMTPException):
        app.logger.exception("Inquiry email delivery failed")
        return jsonify({"status": "error", "message": "Unable to send your inquiry right now. Please call or WhatsApp us."}), 502

    return jsonify({"status": "success", "message": "Thank you. Your inquiry has been sent."})


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=int(os.getenv("PORT", "5000")), debug=False)
