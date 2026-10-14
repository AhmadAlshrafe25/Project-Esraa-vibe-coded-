import os
import sys
import unittest
from unittest.mock import patch
from aiohttp.test_utils import AioHTTPTestCase, unittest_run_loop
from aiohttp import web

# Add project root to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from jarvis.ui.server import EzraUIServer, broadcast_ui_event, set_active_ui_server, get_active_ui_server


class TestEzraUIServer(AioHTTPTestCase):
    async def get_application(self):
        self.ezra_server = EzraUIServer(host="127.0.0.1", port=8089)
        return self.ezra_server.app

    @unittest_run_loop
    async def test_index_page_returns_html(self):
        """GET / must return the Holographic JARVIS UI HTML page."""
        resp = await self.client.get("/")
        self.assertEqual(resp.status, 200)
        self.assertEqual(resp.content_type, "text/html")
        body = await resp.text()
        self.assertIn("PROJECT EZRA", body)
        self.assertIn("JARVIS-CLASS NEURAL CORE", body)
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
        self.assertIn("Crimson Neural Glow", await css_resp.text())

        js_resp = await self.client.get("/static/js/brain_hologram.js")
        self.assertEqual(js_resp.status, 200)
        self.assertIn("EzraBrainHologram", await js_resp.text())

    @patch("subprocess.Popen")
    def test_action_execution(self, mock_popen):
        """_execute_action routes through AppManager.launch_app without errors."""
        res_ag = self.ezra_server._execute_action("open_antigravity")
        self.assertIsInstance(res_ag, dict)
        self.assertIn("status", res_ag)

        res_term = self.ezra_server._execute_action("open_terminal")
        self.assertIsInstance(res_term, dict)
        self.assertIn("status", res_term)

        res_browser = self.ezra_server._execute_action("open_browser")
        self.assertIsInstance(res_browser, dict)
        self.assertIn("status", res_browser)

        res_unk = self.ezra_server._execute_action("unknown_invalid_action")
        self.assertEqual(res_unk, "Unknown action")

    def test_broadcast_ui_event_safe_noop(self):
        """broadcast_ui_event without active server must safely no-op."""
        set_active_ui_server(None, None)
        broadcast_ui_event({"type": "state_change", "state": "listening"})
        broadcast_ui_event("not_a_dict")

    @unittest_run_loop
    async def test_broadcast_ui_event_with_registered_server(self):
        """broadcast_ui_event updates server.current_state and schedules broadcast."""
        self.ezra_server.loop = self.loop
        set_active_ui_server(self.ezra_server, self.loop)
        try:
            broadcast_ui_event({"type": "state_change", "state": "listening"})
            self.assertEqual(self.ezra_server.current_state, "listening")
            broadcast_ui_event({"type": "state_change", "state": "thinking"})
            self.assertEqual(self.ezra_server.current_state, "thinking")
        finally:
            set_active_ui_server(None, None)


if __name__ == "__main__":
    unittest.main()
