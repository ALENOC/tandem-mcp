import importlib
import pathlib
import unittest

SERVICES = ['billing', 'catalog', 'checkout', 'inventory', 'ledger', 'mailer', 'orders', 'pricing', 'reports', 'search', 'shipping', 'users']


class TestRename(unittest.TestCase):
    def test_new_name(self):
        import settings
        self.assertTrue(hasattr(settings, "load_settings"))
        self.assertFalse(hasattr(settings, "get_conf"))
        self.assertEqual(settings.load_settings("retries"), 3)
        self.assertEqual(settings.load_settings("nope", 9), 9)

    def test_no_old_name_left(self):
        for path in pathlib.Path(".").glob("*.py"):
            if path.name != "test_rename.py":
                self.assertNotIn("get_conf", path.read_text(), path.name)

    def test_services_work(self):
        for name in SERVICES:
            mod = importlib.import_module("svc_" + name)
            self.assertEqual(mod.__dict__[name + "_summary"]()["region"], "eu-west-1")
            self.assertTrue(mod.__dict__[name + "_step_0"](list(range(100))))


if __name__ == "__main__":
    unittest.main()
