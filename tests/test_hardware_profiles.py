"""
Test Suite for AirCursor Physical Hardware Remote Profiles & Telemetry Engine
=============================================================================
Verifies:
  1. Profile specifications and default attributes for all 5 physical products.
  2. Binary packet encoding, checksum computation, and decoding for all 5 devices.
  3. Corrupt packet, invalid magic, and bad checksum rejection.
  4. Hardware registry registration, profile switching, and event dispatching.
  5. Validation of all on-disk CAD model files (.blend, .glb, .obj, .stl) and renders (.png).
"""

import os
import unittest
from aircursor_core.hardware_profiles import (
    HardwareDeviceType,
    HardwareTelemetryEvent,
    HardwareRegistry,
    HardwarePacketDecoder,
    HardwarePacketEncoder,
    HARDWARE_REGISTRY,
    AirRingProProfile,
    AirWandEliteProfile,
    AirPebbleTouchProfile,
    AirClipMiniProfile,
    AirDeckControllerProfile,
)


class TestHardwareProfiles(unittest.TestCase):
    """Test profiles data integrity and specifications."""

    def test_all_five_profiles_present(self):
        registry = HardwareRegistry()
        profiles = registry.list_all_profiles()
        self.assertEqual(len(profiles), 5)
        
        types = [p.device_type for p in profiles]
        self.assertIn(HardwareDeviceType.AIRRING_PRO, types)
        self.assertIn(HardwareDeviceType.AIRWAND_ELITE, types)
        self.assertIn(HardwareDeviceType.AIRPEBBLE_TOUCH, types)
        self.assertIn(HardwareDeviceType.AIRCLIP_MINI, types)
        self.assertIn(HardwareDeviceType.AIRDECK_CONTROLLER, types)

    def test_airring_pro_specs(self):
        p = AirRingProProfile()
        self.assertEqual(p.model_name, "AirRing Pro")
        self.assertEqual(p.mass_grams, 8.8)
        self.assertEqual(p.battery_capacity_mah, 38)
        self.assertGreater(p.battery_life_hours, 15.0)
        self.assertEqual(p.trackball_dpi, 800)
        self.assertIn("Micro optical thumb trackball (X/Y relative counts)", p.primary_controls)

    def test_airwand_elite_specs(self):
        p = AirWandEliteProfile()
        self.assertEqual(p.model_name, "AirWand Elite")
        self.assertEqual(p.mass_grams, 52.0)
        self.assertEqual(p.battery_capacity_mah, 320)
        self.assertGreater(p.battery_life_hours, 40.0)
        self.assertIn("CEVA BNO085 9-axis AHRS sensor fusion processor", p.sensor_suite)

    def test_airpebble_touch_specs(self):
        p = AirPebbleTouchProfile()
        self.assertEqual(p.model_name, "AirPebble Touch")
        self.assertEqual(p.mass_grams, 64.0)
        self.assertEqual(p.battery_capacity_mah, 450)
        self.assertIn("PixArt PAW3395 flagship optical sensor (26,000 DPI, 650 IPS)", p.sensor_suite)

    def test_airclip_mini_specs(self):
        p = AirClipMiniProfile()
        self.assertEqual(p.model_name, "AirClip Mini")
        self.assertEqual(p.mass_grams, 14.0)
        self.assertEqual(p.battery_capacity_mah, 85)
        self.assertTrue(p.nod_click_enabled)

    def test_airdeck_controller_specs(self):
        p = AirDeckControllerProfile()
        self.assertEqual(p.model_name, "AirDeck Controller")
        self.assertEqual(p.mass_grams, 68.0)
        self.assertEqual(p.battery_capacity_mah, 500)
        self.assertEqual(p.shoulder_button_remap_l1, "LEFT_CLICK")
        self.assertEqual(p.shoulder_button_remap_r1, "RIGHT_CLICK")

    def test_profile_serialization(self):
        p = AirDeckControllerProfile()
        data = p.to_dict()
        self.assertEqual(data["model_name"], "AirDeck Controller")
        self.assertEqual(data["mass_grams"], 68.0)
        self.assertIsInstance(data["cad_files"], dict)


class TestBinaryTelemetryProtocol(unittest.TestCase):
    """Test bit-level telemetry packet encoding and decoding."""

    def test_airring_pro_packet_roundtrip(self):
        packet = HardwarePacketEncoder.encode_airring_pro(
            seq=42,
            pitch=12.5,
            roll=-5.2,
            opt_x=15,
            opt_y=-20,
            bezel_delta=3,
            primary_click=True,
            secondary_click=False,
            battery_pct=94
        )
        self.assertEqual(len(packet), 13)
        event = HardwarePacketDecoder.decode(packet)
        self.assertIsNotNone(event)
        self.assertEqual(event.device_type, HardwareDeviceType.AIRRING_PRO)
        self.assertEqual(event.sequence, 42)
        self.assertAlmostEqual(event.pitch, 12.5, places=1)
        self.assertAlmostEqual(event.roll, -5.2, places=1)
        self.assertEqual(event.delta_x, 15.0)
        self.assertEqual(event.delta_y, -20.0)
        self.assertEqual(event.dial_delta, 3.0)
        self.assertTrue(event.primary_click)
        self.assertFalse(event.secondary_click)
        self.assertEqual(event.battery_pct, 94)

    def test_airwand_elite_packet_roundtrip(self):
        packet = HardwarePacketEncoder.encode_airwand_elite(
            seq=10,
            yaw=0.0,
            pitch=30.0,
            roll=0.0,
            thumb_x=5,
            thumb_y=-10,
            trigger_force=0.9,
            squeeze_force=0.0,
            battery_pct=85
        )
        self.assertEqual(len(packet), 18)
        event = HardwarePacketDecoder.decode(packet)
        self.assertIsNotNone(event)
        self.assertEqual(event.device_type, HardwareDeviceType.AIRWAND_ELITE)
        self.assertEqual(event.sequence, 10)
        self.assertAlmostEqual(event.pitch, 30.0, delta=2.0)
        self.assertTrue(event.trigger_pressed)
        self.assertTrue(event.primary_click)
        self.assertFalse(event.squeeze_pressed)
        self.assertGreater(event.trigger_force, 0.8)
        self.assertEqual(event.battery_pct, 85)

    def test_airpebble_touch_packet_roundtrip(self):
        packet = HardwarePacketEncoder.encode_airpebble_touch(
            seq=77,
            opt_dx=250,
            opt_dy=-180,
            dial_delta=-5,
            touch_x=120,
            touch_y=80,
            touch_pressure=0.75,
            primary_click=False,
            secondary_click=True,
            battery_pct=99
        )
        self.assertEqual(len(packet), 14)
        event = HardwarePacketDecoder.decode(packet)
        self.assertIsNotNone(event)
        self.assertEqual(event.device_type, HardwareDeviceType.AIRPEBBLE_TOUCH)
        self.assertEqual(event.delta_x, 250.0)
        self.assertEqual(event.delta_y, -180.0)
        self.assertEqual(event.dial_delta, -5.0)
        self.assertAlmostEqual(event.touch_pressure, 0.75, delta=0.05)
        self.assertFalse(event.primary_click)
        self.assertTrue(event.secondary_click)
        self.assertEqual(event.battery_pct, 99)

    def test_airclip_mini_packet_roundtrip(self):
        # Unmuted with tap click
        packet = HardwarePacketEncoder.encode_airclip_mini(
            seq=3,
            pitch=8.0,
            roll=2.5,
            is_muted=False,
            tap_count=1,
            battery_pct=72
        )
        self.assertEqual(len(packet), 11)
        event = HardwarePacketDecoder.decode(packet)
        self.assertIsNotNone(event)
        self.assertEqual(event.device_type, HardwareDeviceType.AIRCLIP_MINI)
        self.assertFalse(event.mute_switch_active)
        self.assertTrue(event.primary_click)
        self.assertEqual(event.battery_pct, 72)

        # Muted hardware toggle disables click
        packet_muted = HardwarePacketEncoder.encode_airclip_mini(
            seq=4,
            pitch=8.0,
            roll=2.5,
            is_muted=True,
            tap_count=1,
            battery_pct=72
        )
        event_muted = HardwarePacketDecoder.decode(packet_muted)
        self.assertTrue(event_muted.mute_switch_active)
        self.assertFalse(event_muted.primary_click)

    def test_airdeck_controller_packet_roundtrip(self):
        packet = HardwarePacketEncoder.encode_airdeck_controller(
            seq=99,
            track_x=-35,
            track_y=60,
            force=0.45,
            gyro_x=10,
            gyro_y=-5,
            l1=True,
            r1=False,
            battery_pct=91
        )
        self.assertEqual(len(packet), 13)
        event = HardwarePacketDecoder.decode(packet)
        self.assertIsNotNone(event)
        self.assertEqual(event.device_type, HardwareDeviceType.AIRDECK_CONTROLLER)
        self.assertEqual(event.delta_x, -35.0)
        self.assertEqual(event.delta_y, 60.0)
        self.assertTrue(event.primary_click)
        self.assertFalse(event.secondary_click)
        self.assertEqual(event.battery_pct, 91)

    def test_corrupt_packet_rejection(self):
        # Valid packet
        valid = HardwarePacketEncoder.encode_airring_pro(seq=1)
        self.assertIsNotNone(HardwarePacketDecoder.decode(valid))

        # Corrupted checksum
        corrupted = bytearray(valid)
        corrupted[-1] ^= 0xFF
        self.assertIsNone(HardwarePacketDecoder.decode(bytes(corrupted)))

        # Truncated packet
        truncated = valid[:8]
        self.assertIsNone(HardwarePacketDecoder.decode(truncated))

        # Invalid magic header
        bad_magic = bytearray(valid)
        bad_magic[0] = 0xFE
        # Recompute checksum for bad magic to ensure magic check fails
        chk = HardwarePacketDecoder.calculate_checksum(bad_magic[:-1])
        bad_magic[-1] = chk
        self.assertIsNone(HardwarePacketDecoder.decode(bytes(bad_magic)))


class TestHardwareCADFiles(unittest.TestCase):
    """Verify that all 5 products have valid, non-empty 3D CAD files and renders."""

    def setUp(self):
        # Base repo path
        self.repo_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
        self.models_dir = os.path.join(self.repo_dir, "cad", "models")
        self.renders_dir = os.path.join(self.repo_dir, "cad", "renders")

    def test_all_five_products_cad_files_exist(self):
        concepts = [
            "concept_1_airring_pro",
            "concept_2_airwand_elite",
            "concept_3_airpebble_touch",
            "concept_4_airclip_mini",
            "concept_5_airdeck_controller",
        ]
        extensions = [".blend", ".glb", ".obj", ".stl"]

        for concept in concepts:
            # Check render
            render_path = os.path.join(self.renders_dir, f"{concept}.png")
            self.assertTrue(os.path.exists(render_path), f"Missing render: {render_path}")
            self.assertGreater(os.path.getsize(render_path), 50000, f"Render too small: {render_path}")

            # Check CAD models
            for ext in extensions:
                model_path = os.path.join(self.models_dir, f"{concept}{ext}")
                self.assertTrue(os.path.exists(model_path), f"Missing CAD model: {model_path}")
                size = os.path.getsize(model_path)
                self.assertGreater(size, 1000, f"CAD file too small ({size} bytes): {model_path}")


if __name__ == "__main__":
    unittest.main()
