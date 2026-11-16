import sys
import unittest
from unittest.mock import patch, MagicMock
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))
sys.path.insert(0, str(ROOT_DIR / "windows"))

import ctypes
user32 = ctypes.windll.user32
h_winsta = user32.OpenWindowStationW("WinSta0", False, 0x10000000)
if h_winsta:
    user32.SetProcessWindowStation(h_winsta)
h_desk = user32.OpenDesktopW("Default", 0, False, 0x10000000)
if h_desk:
    user32.SetThreadDesktop(h_desk)

import tkinter as tk
from control_center import PhysicalRemotesDialog
from aircursor_core.hardware_profiles import HARDWARE_REGISTRY

class TestPhysicalRemotesCompanionDialog(unittest.TestCase):
    def setUp(self):
        self.root = tk.Tk()
        self.root.withdraw()
        self.mock_controller = MagicMock()

    def tearDown(self):
        try:
            self.root.destroy()
        except Exception:
            pass

    def test_companion_dialog_lifecycle_and_selection(self):
        dialog = PhysicalRemotesDialog(self.root, self.mock_controller)
        self.assertIsNotNone(dialog)
        self.assertEqual(len(dialog.profiles), 5)
        
        # Test switching across all 5 physical hardware products
        for idx in range(5):
            dialog._select_product(idx)
            expected_name = dialog.profiles[idx].model_name
            self.assertIn(expected_name, dialog.lbl_dev_name.cget("text"))
            self.assertIn("g", dialog.lbl_mass_badge.cget("text"))
            self.assertIn("Battery", dialog.lbl_batt_badge.cget("text"))
        
        # Test packet injection across all 5 products
        for idx in range(5):
            dialog._select_product(idx)
            dialog._inject_test_packet()
            status_text = dialog.lbl_inject_status.cget("text")
            self.assertIn("Decoded", status_text)
            self.assertIn(dialog.profiles[idx].model_name, status_text)

        # Test WebGL 3D launch button
        with patch("webbrowser.open") as mock_open:
            dialog._launch_webgl()
            self.assertTrue(mock_open.called)
            uri = mock_open.call_args[0][0]
            self.assertIn("remote_showcase.html", uri)

        dialog.destroy()

if __name__ == "__main__":
    unittest.main()
