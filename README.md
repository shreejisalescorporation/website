```markdown
# 🌐 Shreeji Sales Corporation – Official Website

Welcome to the official website repository of **Shreeji Sales Corporation**, a leading plywood wholesaler based in Ahmedabad.

This website serves as a digital portfolio for the company and uses Brevo transactional email to deliver business inquiries.

---

## 🛠️ Tech Stack

- **Frontend**: HTML, CSS, JavaScript
- **Backend**: Python (Flask)
- **Hosting**: Render

---

## 🚀 Features

- 🖼️ Company Portfolio Showcase
- 📬 Contact Form with Brevo Email Delivery
- 📱 Responsive Design (Mobile + Desktop)
- ⚡ Fast Page Load and Clean UI
- 🔒 Form Validation and Basic Spam Protection

---

## 📧 Brevo Email Configuration

Configure these environment variables on the Flask API host:

- `BREVO_API_KEY`: Brevo API key with transactional email permissions.
- `BREVO_SENDER_EMAIL`: A sender address verified in Brevo.
- `BREVO_SENDER_NAME`: Optional sender display name (defaults to `Shreeji Sales Corporation`).
- `INQUIRY_RECEIVER_EMAIL`: Optional sales inbox (defaults to `shreejisalescorp.in@gmail.com`).
- `RECAPTCHA_SECRET_KEY`: The production reCAPTCHA secret. The legacy `secretkeycap` variable remains supported for existing deployments.
- `TRUSTED_PROXY_COUNT`: Number of trusted reverse proxies in front of the API. Defaults to `0`; set this only to the verified proxy count so forwarded client IPs are not accepted from arbitrary callers.
- `LOCAL_RECAPTCHA_TEST_SECRET`: Optional local-only secret. It is used only when the direct client connection is loopback; configure it locally and never commit it.

The API sends the inquiry to the sales inbox first. It sends the customer confirmation only after Brevo accepts the sales notification. Do not commit the API key to source control.

## 🚀 Production API

Run the API with the production WSGI server rather than Flask's development server:

```sh
gunicorn --bind 0.0.0.0:$PORT app:app
```

The API's in-process inquiry throttle is per worker and is intended as a secondary control. Keep the hosting platform's edge/WAF rate limits enabled for production traffic. The `/healthz` endpoint is a lightweight liveness check; it does not prove that Brevo or reCAPTCHA is reachable.

The static site and Flask API are separate deployment surfaces. Configure security response headers at the static hosting/CDN layer as well as on the Flask API; Flask headers do not protect pages served directly by GitHub Pages or another static host.

The API accepts inquiry submissions from `shreejisalescorp.in`, `www.shreejisalescorp.in`, `api.shreejisalescorp.in`, and the configured GitHub Pages origin. The API hostname is allowed because the Flask service also serves the contact page there.

## ✅ Local checks

```sh
python -m unittest discover -s tests -v
```

---

## 🔒 Access

This repository is maintained by **Shreeji Sales Corporation** and may contain proprietary business logic. Please contact us for collaboration or demonstration access.

---

## 👨‍💻 Developed By

This website was developed by [Priyan Bhatt](https://github.com/priyanbhatt), in collaboration with Shreeji Sales Corporation.

---

For any issues or feature requests, please contact:
📧 **shreejisalescorp.in@gmail.com**
```
