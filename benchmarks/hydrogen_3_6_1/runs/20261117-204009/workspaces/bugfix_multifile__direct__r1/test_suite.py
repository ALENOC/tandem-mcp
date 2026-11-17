import unittest
from service import build_config


class TestServiceConfig(unittest.TestCase):
    def test_explicit_port_without_ssl(self):
        cfg = build_config("postgres://db.internal:6432/app", ssl=False, timeout_ms=2500)
        self.assertEqual(cfg.host, "db.internal")
        self.assertEqual(cfg.port, 6432)
        self.assertFalse(cfg.ssl)
        self.assertEqual(cfg.database, "app")

    def test_default_port_with_ssl(self):
        cfg = build_config("postgres://db.internal/prod", ssl=True, timeout_ms=1000)
        self.assertEqual(cfg.port, 5433)
        self.assertTrue(cfg.ssl)

    def test_zero_timeout_allowed(self):
        cfg = build_config("postgres://localhost:5432/test", ssl=False, timeout_ms=0)
        self.assertEqual(cfg.timeout_ms, 0)

    def test_negative_timeout_rejected(self):
        with self.assertRaises(ValueError):
            build_config("postgres://localhost/test", timeout_ms=-1)


if __name__ == "__main__":
    unittest.main()
