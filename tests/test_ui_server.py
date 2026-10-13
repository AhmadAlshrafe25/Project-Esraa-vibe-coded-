import os
import sys
import unittest
from aiohttp.test_utils import AioHTTPTestCase, unittest_run_loop
from aiohttp import web

# Add project root to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from jarvis.ui.server import EzraUIServer


class TestEzraUIServer(AioHTTPTestCase):
    async def get_application(self):
        self.server = EzraUIServer(host="127.0.0.1", port=8089)
        return self.server.app

    @unittest_run_loop
    async def test_index_page_returns_html(self):
        """GET / must return the Holographic JARVIS UI HTML page."""
        resp = await self.client.get("/")
        self.assertEqual(resp.status, 200)
        self.assertEqual(resp.content_type, "text/html")
        body = await resp.text()
        self.assertIn("PROJECT EZRA", body)
        self.assertIn("HOLOGRAPHIC NEURAL CORE", body)
        self.assertIn("brainCanvas", body)

    @unittest_run_loop
    async def test_api_status_telemetry(self):
        """GET /api/status must return valid JSON system vitals and Ezra status."""
        resp = await self.client.get("/api/status")
        self.assertEqual(resp.status, 200)
        self.assertEqual(resp.content_type, "application/json")
        data = await resp.json()
        self.assertEqual(data.get("type"), "telemetry")
        self.assertIn("cpu", data)
        self.assertIn("ram", data)
        self.assertIn("uptime", data)
        self.assertIn("distro", data)
        self.assertIn("engine", data)

    @unittest_run_loop
    async def test_static_assets_serving(self):
        """GET /static/css/style.css and /static/js/brain_hologram.js must return 200."""
        css_resp = await self.client.get("/static/css/style.css")
        self.assertEqual(css_resp.status, 200)
        self.assertIn("crimson-core", await css_resp.text())

        js_resp = await self.client.get("/static/js/brain_hologram.js")
        self.assertEqual(js_resp.status, 200)
        self.assertIn("EzraBrainHologram", await js_resp.text())


if __name__ == "__main__":
    unittest.main()
