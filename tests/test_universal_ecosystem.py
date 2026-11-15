import unittest
from aircursor_core.arbiter import SourceArbiter, SourcePriority
from aircursor_core.pairing_qr import pairing_url

class ArbiterTests(unittest.TestCase):
    def test_priority_and_stale_failover(self):
        a=SourceArbiter(stale_after=2)
        self.assertEqual(a.update("remote",SourcePriority.REMOTE,connected=True,now=1),"remote")
        self.assertEqual(a.update("vision",SourcePriority.VISION,connected=True,now=1),"vision")
        self.assertEqual(a.update("airpods",SourcePriority.AIRPODS,connected=True,now=1),"airpods")
        self.assertIsNone(a.active_source(now=4))
    def test_disabled_source_is_ignored(self):
        a=SourceArbiter()
        self.assertIsNone(a.update("camera",SourcePriority.VISION,connected=True,enabled=False,now=10))

class PairingTests(unittest.TestCase):
    def test_token_is_fragment(self):
        self.assertEqual(pairing_url("http://192.168.1.4:8765/","secret"),"http://192.168.1.4:8765/#secret")
    def test_invalid_url_rejected(self):
        with self.assertRaises(ValueError): pairing_url("file:///tmp/remote","secret")

if __name__ == "__main__": unittest.main()
