import json
import os
from pathlib import Path
import tempfile
import unittest

from migrate import migrate, migrate_file, PLUGIN_ID


class Migration(unittest.TestCase):
    def test_preserves_rules_connection_placement_and_other_plugins(self):
        old = {"id": "ha.watch", "url": "http://ha.local", "clientId": "http://127.0.0.1:1234/",
               "rules": [{"sensor": "cover.garage", "states": ["open"], "messages": {"open": "Garage open"}}]}
        config = {"bar": {"layout": {"right": [{"id": "omarchy.clock"}, old]}}, "idle": {"lock": 300}}
        result = migrate(config)
        self.assertEqual(result["bar"]["layout"]["right"][1], {**old, "id": PLUGIN_ID})
        self.assertEqual(config["bar"]["layout"]["right"][1]["id"], "ha.watch")
        self.assertEqual(migrate(result), result)
        self.assertEqual(result["idle"], config["idle"])

    def test_conflicting_installations_are_not_overwritten(self):
        with self.assertRaises(ValueError):
            migrate({"plugins": [{"id": "ha.watch"}, {"id": PLUGIN_ID}]})

    def test_private_backup_and_idempotence(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "shell.json"
            original = json.dumps({"plugins": [{"id": "ha.watch", "rules": []}]})
            path.write_text(original)
            backup = migrate_file(path)
            self.assertEqual(Path(backup).read_text(), original)
            self.assertEqual(os.stat(backup).st_mode & 0o777, 0o600)
            self.assertEqual(json.loads(path.read_text())["plugins"][0]["id"], PLUGIN_ID)
            self.assertIsNone(migrate_file(path))

    def test_no_settings_and_disabled_entries(self):
        self.assertEqual(migrate({}), {})
        self.assertEqual(migrate({"disabledPlugins": ["ha.watch"]}), {"disabledPlugins": [PLUGIN_ID]})


if __name__ == "__main__":
    unittest.main()
