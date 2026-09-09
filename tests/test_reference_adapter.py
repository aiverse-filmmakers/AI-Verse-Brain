import unittest
from pathlib import Path

from aiverse_brain.bridge import BridgeConfig, adapter_doctor


ROOT = Path(__file__).resolve().parents[1]


class ReferenceAdapterTests(unittest.TestCase):
    def test_checked_in_reference_adapter_handshakes(self):
        config = BridgeConfig.load(str(ROOT / "examples" / "reference-adapter.json"))
        report = adapter_doctor(config)
        self.assertTrue(report["ok"])
        self.assertEqual(report["adapter_id"], "reference-bridge")
        self.assertEqual(report["protocol_version"], "1.0")
        self.assertIn("reason", report["operations"])
        self.assertIn("read_context", report["operations"])
        self.assertFalse(report["idempotency_supported"])
        self.assertFalse(report["credential_values_stored"])


if __name__ == "__main__":
    unittest.main()
