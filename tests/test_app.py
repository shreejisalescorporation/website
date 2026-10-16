import os
from html.parser import HTMLParser
from pathlib import Path
import unittest
from urllib.parse import urlparse
from unittest.mock import patch
from xml.etree import ElementTree

import app as app_module
from app import (
    ARTICLE_ROUTE_FILES,
    SITE_ROUTE_DIRS,
    _client_address,
    _form_value,
    _is_local_request,
    _is_rate_limited,
    app,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
BASE_URL = "https://shreejisalescorp.in"


class PageMetadataParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.title = ""
        self.in_title = False
        self.meta = {}
        self.properties = {}
        self.canonical = None

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        if tag == "title":
            self.in_title = True
        if tag == "meta":
            if attributes.get("name"):
                self.meta[attributes["name"]] = attributes.get("content", "")
            if attributes.get("property"):
                self.properties[attributes["property"]] = attributes.get("content", "")
        if tag == "link" and attributes.get("rel") == "canonical":
            self.canonical = attributes.get("href")

    def handle_endtag(self, tag):
        if tag == "title":
            self.in_title = False

    def handle_data(self, data):
        if self.in_title:
            self.title += data


class InquiryAppTests(unittest.TestCase):
    def setUp(self):
        app.config.update(TESTING=True)
        app_module._recent_requests.clear()
        self.client = app.test_client()

    def test_known_pages_redirect_to_canonical_trailing_slash(self):
        for page in SITE_ROUTE_DIRS | set(ARTICLE_ROUTE_FILES):
            with self.subTest(page=page):
                response = self.client.get(f"/{page}")
                self.assertEqual(response.status_code, 308)
                self.assertEqual(response.headers["Location"], f"/{page}/")
                self.assertEqual(self.client.get(f"/{page}/").status_code, 200)

    def test_unknown_path_is_not_served_as_homepage(self):
        response = self.client.get("/this-page-does-not-exist/")
        self.assertEqual(response.status_code, 404)

    def test_health_check_and_security_headers(self):
        response = self.client.get("/healthz")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json, {"status": "ok"})
        self.assertEqual(response.headers["X-Content-Type-Options"], "nosniff")
        self.assertEqual(response.headers["X-Frame-Options"], "SAMEORIGIN")
        self.assertIn("default-src 'self'", response.headers["Content-Security-Policy"])

    def test_https_responses_receive_hsts(self):
        response = self.client.get("/healthz", base_url="https://shreejisalescorp.in")
        self.assertIn("max-age=31536000", response.headers["Strict-Transport-Security"])

    def test_host_header_does_not_make_remote_peer_local(self):
        with app.test_request_context(
            "/",
            base_url="http://localhost",
            environ_base={"REMOTE_ADDR": "203.0.113.8"},
        ):
            self.assertFalse(_is_local_request())

    def test_forwarded_for_is_not_trusted_without_proxy_fix(self):
        with app.test_request_context(
            "/",
            environ_base={"REMOTE_ADDR": "203.0.113.8"},
            headers={"X-Forwarded-For": "198.51.100.9"},
        ):
            self.assertEqual(_client_address(), "203.0.113.8")

    def test_inquiry_throttle_limits_a_single_client(self):
        with app.test_request_context(
            "/send_inquiry",
            environ_base={"REMOTE_ADDR": "203.0.113.10"},
        ):
            for _ in range(6):
                self.assertFalse(_is_rate_limited())
            self.assertTrue(_is_rate_limited())

    def test_remote_host_spoof_cannot_select_local_recaptcha_secret(self):
        form = {
            "name": "Test User",
            "email": "customer@example.com",
            "phone": "+91 98765 43210",
            "city": "Ahmedabad",
            "message": "Please share a quotation.",
            "g-recaptcha-response": "test-token",
        }
        mock_response = SuccessfulResponse()
        with patch.dict(
            os.environ,
            {
                "RECAPTCHA_SECRET_KEY": "production-secret",
                "LOCAL_RECAPTCHA_TEST_SECRET": "local-test-secret",
                "BREVO_API_KEY": "test-api-key",
                "BREVO_SENDER_EMAIL": "sales@example.com",
                "INQUIRY_RECEIVER_EMAIL": "receiver@example.com",
            },
        ), patch("app.requests.post", return_value=mock_response) as post:
            response = self.client.post(
                "/send_inquiry",
                data=form,
                headers={"Host": "localhost"},
                environ_overrides={"REMOTE_ADDR": "203.0.113.8"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(post.call_args_list[0].kwargs["data"]["secret"], "production-secret")

    def test_invalid_origin_is_rejected(self):
        response = self.client.post(
            "/send_inquiry",
            data={},
            headers={"Origin": "https://attacker.example"},
        )
        self.assertEqual(response.status_code, 403)

    def test_inquiry_fields_reject_control_characters(self):
        with app.test_request_context("/", method="POST", data={"name": "name\r\nBcc: victim@example.com"}):
            with self.assertRaises(ValueError):
                _form_value("name", 100)

    def test_message_allows_newlines_but_not_other_control_characters(self):
        with app.test_request_context("/", method="POST", data={"message": "Line one\nLine two"}):
            self.assertEqual(_form_value("message", 2000, minimum_length=5, allow_line_breaks=True), "Line one\nLine two")
        with app.test_request_context("/", method="POST", data={"message": "Line one\x00Line two"}):
            with self.assertRaises(ValueError):
                _form_value("message", 2000, minimum_length=5, allow_line_breaks=True)

    def test_oversized_requests_return_json_413(self):
        response = self.client.post("/send_inquiry", data={"message": "x" * 70_000})
        self.assertEqual(response.status_code, 413)
        self.assertEqual(response.json["status"], "error")


class SuccessfulResponse:
    ok = True

    @staticmethod
    def raise_for_status():
        return None

    @staticmethod
    def json():
        return {"success": True}


class SeoTests(unittest.TestCase):
    def test_served_pages_have_unique_titles_descriptions_and_canonicals_in_sitemap(self):
        page_files = [PROJECT_ROOT / "index.html"]
        page_files.extend(PROJECT_ROOT / route / "index.html" for route in SITE_ROUTE_DIRS)
        page_files.extend(PROJECT_ROOT / path for path in ARTICLE_ROUTE_FILES.values())

        sitemap_root = ElementTree.parse(PROJECT_ROOT / "sitemap.xml").getroot()
        sitemap_urls = {
            element.text
            for element in sitemap_root.iter("{http://www.sitemaps.org/schemas/sitemap/0.9}loc")
        }
        titles = set()
        canonicals = set()

        for page in page_files:
            parser = PageMetadataParser()
            parser.feed(page.read_text(encoding="utf-8"))
            with self.subTest(page=page.relative_to(PROJECT_ROOT)):
                self.assertTrue(parser.title.strip())
                self.assertTrue(parser.meta.get("description", "").strip())
                self.assertTrue(parser.canonical)
                self.assertEqual(parser.canonical, parser.canonical.strip())
                self.assertTrue(parser.canonical.startswith(BASE_URL + "/"))
                self.assertIn(parser.canonical, sitemap_urls)
                self.assertNotIn(parser.title, titles)
                self.assertNotIn(parser.canonical, canonicals)
                titles.add(parser.title)
                canonicals.add(parser.canonical)

        self.assertEqual(canonicals, sitemap_urls)

    def test_product_landing_pages_have_complete_social_cards_and_zoomable_viewports(self):
        routes = {"alt", "bb", "comm", "mdf", "mr", "pack", "plywood", "timnlam"}

        for route in routes:
            page = PROJECT_ROOT / route / "index.html"
            parser = PageMetadataParser()
            parser.feed(page.read_text(encoding="utf-8"))
            with self.subTest(route=route):
                self.assertEqual(parser.properties.get("og:url"), f"{BASE_URL}/{route}/")
                self.assertTrue(parser.properties.get("og:title"))
                self.assertTrue(parser.properties.get("og:description"))
                image_url = parser.properties.get("og:image", "")
                self.assertTrue(image_url.startswith(BASE_URL + "/"))
                self.assertTrue((PROJECT_ROOT / urlparse(image_url).path.lstrip("/")).is_file())
                self.assertEqual(parser.meta.get("twitter:card"), "summary_large_image")
                self.assertTrue(parser.meta.get("twitter:title"))
                self.assertTrue(parser.meta.get("twitter:description"))
                viewport = parser.meta.get("viewport", "").lower()
                self.assertNotIn("user-scalable=no", viewport)
                self.assertNotIn("maximum-scale=1", viewport)


if __name__ == "__main__":
    unittest.main()
