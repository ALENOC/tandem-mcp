import unittest
from config_loader import parse_endpoint
from formatter import format_summary

class TestConfig(unittest.TestCase):
    def test_tls_endpoint(self):
        ep = parse_endpoint({"host": "api.local", "port": 8443, "tls": "true"})
        self.assertEqual(ep.url(), "https://api.local:8443")

    def test_plain_custom_port(self):
        ep = parse_endpoint({"host": "api.local", "port": 9000, "tls": "false"})
        self.assertEqual(ep.url(), "http://api.local:9000")
        self.assertIn("http://api.local:9000", format_summary(ep, True))

if __name__ == "__main__":
    unittest.main()
