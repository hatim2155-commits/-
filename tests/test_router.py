from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import threading
import unittest

from core.router import HuaweiRouter


class RouterProtocolTests(unittest.TestCase):
    def setUp(self):
        self.requests = []
        self.include_home_token = True

        class Handler(BaseHTTPRequestHandler):
            def do_GET(handler):
                self.requests.append(("GET", handler.path, handler.headers.get("Cookie"), handler.headers.get("__RequestVerificationToken")))
                if handler.path == "/":
                    handler.send_response(200)
                    if self.include_home_token:
                        handler.send_header("Set-Cookie", "SessionID=router-session; Path=/")
                        body = b'<html><meta name="csrf_token" content="initial-token"></html>'
                    else:
                        body = b"<html></html>"
                    handler.end_headers()
                    handler.wfile.write(body)
                elif handler.path == "/api/webserver/token":
                    handler.send_response(404)
                    handler.end_headers()
                elif handler.path == "/api/webserver/SesTokInfo":
                    handler.send_response(200)
                    handler.end_headers()
                    handler.wfile.write(b"<response><SesInfo>router-session</SesInfo><TokInfo>initial-token</TokInfo></response>")
                elif handler.path == "/api/user/state-login":
                    handler.send_response(200)
                    handler.send_header("__RequestVerificationToken", "state-token")
                    handler.end_headers()
                    handler.wfile.write(b"<response><State>-1</State><password_type>0</password_type></response>")
                elif handler.path == "/api/device/signal":
                    handler.send_response(200)
                    handler.end_headers()
                    handler.wfile.write(b"<response><rsrp>-95dBm</rsrp><rsrq>-10dB</rsrq><sinr>15dB</sinr><pci>44</pci></response>")
                elif handler.path == "/api/net/cell-info":
                    handler.send_response(200)
                    handler.end_headers()
                    handler.wfile.write(b"<response><cell_id>123456</cell_id><pci>44</pci></response>")
                else:
                    handler.send_response(404)
                    handler.end_headers()

            def do_POST(handler):
                length = int(handler.headers.get("Content-Length", "0"))
                body = handler.rfile.read(length).decode("utf-8")
                self.requests.append(("POST", handler.path, handler.headers.get("Cookie"), handler.headers.get("__RequestVerificationToken"), body))
                handler.send_response(200)
                handler.send_header("__RequestVerificationTokenone", "authenticated-token")
                handler.end_headers()
                handler.wfile.write(b"<response>OK</response>")

            def log_message(self, *_args):
                pass

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.address = f"http://127.0.0.1:{self.server.server_port}"

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)

    def test_keeps_huawei_cookie_tokens_and_login_state(self):
        reading = HuaweiRouter.test_connection(self.address, "secret")

        self.assertTrue(reading.login_verified)
        self.assertEqual(reading.signal["4G LTE"]["RSRP"], "-95 dBm")
        self.assertEqual(reading.cell_info["معرّف الخلية"], "123456")

        state_request = next(entry for entry in self.requests if entry[1] == "/api/user/state-login")
        login_request = next(entry for entry in self.requests if entry[0] == "POST")
        signal_request = next(entry for entry in self.requests if entry[1] == "/api/device/signal")
        self.assertIn("SessionID=router-session", state_request[2])
        self.assertEqual(state_request[3], "initial-token")
        self.assertIn("SessionID=router-session", login_request[2])
        self.assertEqual(login_request[3], "state-token")
        self.assertIn("<Username>admin</Username>", login_request[4])
        self.assertTrue(signal_request[3])

    def test_signal_request_works_without_stored_password(self):
        reading = HuaweiRouter.test_connection(self.address)

        self.assertFalse(reading.login_verified)
        self.assertEqual(reading.signal["4G LTE"]["PCI"], "44")
        self.assertFalse(any(request[0] == "POST" for request in self.requests))

    def test_uses_sestokinfo_session_cookie_when_homepage_has_no_token(self):
        self.include_home_token = False
        reading = HuaweiRouter.test_connection(self.address, "secret")

        self.assertTrue(reading.login_verified)
        state_request = next(entry for entry in self.requests if entry[1] == "/api/user/state-login")
        self.assertIn("SessionID=router-session", state_request[2])
        self.assertEqual(state_request[3], "initial-token")


if __name__ == "__main__":
    unittest.main()
