"""Comprehensive test suite for aircursor_core.

Directly ports and validates all test cases from:
- Tests/AirCursorCoreTests/PointerTests.swift
- Tests/AirCursorCoreTests/GestureTests.swift
- Tests/AirCursorCoreTests/UpdateTests.swift
Plus additional boundary, mathematical equivalence, and edge case tests.
"""

from __future__ import annotations

import math
import os
import sys
import unittest

# Ensure aircursor_core is importable
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from aircursor_core import (
    ActionMap,
    AngleMath,
    AppSettings,
    AppVersion,
    DwellDetector,
    DwellSettings,
    GestureDetector,
    GestureEvent,
    GestureSettings,
    HeadGesture,
    MotionDifferentiator,
    MotionSample,
    PointerAction,
    PointerMapper,
    PointerSettings,
    PointerSmoother,
    ReleaseAsset,
    ReleaseInfo,
    ReleaseNotes,
    Trigger,
    UpdatePolicy,
    Vec2,
)
from aircursor_core.pointer import CursorHistory


class TestMathUtil(unittest.TestCase):
    """Tests for Vec2 and AngleMath."""

    def test_vec2_arithmetic(self):
        v1 = Vec2(3.0, 4.0)
        self.assertEqual(v1.length, 5.0)
        self.assertEqual(Vec2.zero, Vec2(0.0, 0.0))

        v2 = Vec2(1.0, 2.0)
        added = v1 + v2
        self.assertEqual(added, Vec2(4.0, 6.0))

        subbed = v1 - v2
        self.assertEqual(subbed, Vec2(2.0, 2.0))

        scaled = v2 * 3.0
        self.assertEqual(scaled, Vec2(3.0, 6.0))
        rscaled = 3.0 * v2
        self.assertEqual(rscaled, Vec2(3.0, 6.0))

        divided = v1 / 2.0
        self.assertEqual(divided, Vec2(1.5, 2.0))

        neg = -v1
        self.assertEqual(neg, Vec2(-3.0, -4.0))

        dist = v1.distance(Vec2(0.0, 0.0))
        self.assertEqual(dist, 5.0)

        # Iteration / unpacking
        x, y = v1
        self.assertEqual((x, y), (3.0, 4.0))

    def test_angle_math_conversions(self):
        self.assertAlmostEqual(AngleMath.degrees(math.pi), 180.0, places=9)
        self.assertAlmostEqual(AngleMath.radians(180.0), math.pi, places=9)
        self.assertAlmostEqual(AngleMath.degrees(math.pi / 2), 90.0, places=9)
        self.assertAlmostEqual(AngleMath.radians(90.0), math.pi / 2, places=9)

    def test_angle_math_wrapping(self):
        # Difference across +-pi
        delta = AngleMath.wrapped_delta(-math.pi + 0.01, math.pi - 0.01)
        self.assertAlmostEqual(delta, 0.02, places=6)

        delta_deg = AngleMath.wrapped_delta_degrees(-179.0, 179.0)
        self.assertAlmostEqual(delta_deg, 2.0, places=6)

        delta_deg_rev = AngleMath.wrapped_delta_degrees(179.0, -179.0)
        self.assertAlmostEqual(delta_deg_rev, -2.0, places=6)

        # Difference exactly within range
        self.assertAlmostEqual(AngleMath.wrapped_delta_degrees(45.0, 15.0), 30.0, places=6)
        self.assertAlmostEqual(AngleMath.wrapped_delta_degrees(15.0, 45.0), -30.0, places=6)


class TestPointer(unittest.TestCase):
    """Corresponds to PointerTests.swift."""

    def test_deadzone_holds_still(self):
        s = PointerSettings()
        s.deadzone = 5.0
        self.assertEqual(PointerMapper.axis_speed(4.9, settings=s), 0.0)
        self.assertEqual(PointerMapper.axis_speed(-4.9, settings=s), 0.0)
        self.assertGreater(PointerMapper.axis_speed(6.0, settings=s), 0.0)

    def test_speed_is_symmetric_and_monotonic(self):
        s = PointerSettings()
        previous = 0.0
        rate = 5.0
        while rate <= 300.0:
            v = PointerMapper.axis_speed(rate, settings=s)
            self.assertAlmostEqual(v, -PointerMapper.axis_speed(-rate, settings=s), places=9)
            self.assertGreaterEqual(v, previous)
            previous = v
            rate += 5.0

    def test_sensitivity_scales_linearly(self):
        s = PointerSettings()
        base = PointerMapper.axis_speed(40.0, settings=s)
        s.sensitivity = 2.0
        self.assertAlmostEqual(PointerMapper.axis_speed(40.0, settings=s), base * 2.0, places=9)

    def test_directions_and_inversion(self):
        s = PointerSettings()
        s.deadzone = 0.0
        # Turn left (+yaw) -> cursor left (-x). Look up (+pitch) -> cursor up (-y).
        rates = MotionDifferentiator()  # test with AngularRates
        from aircursor_core.motion import AngularRates

        r = AngularRates(timestamp=0.0, yaw=30.0, pitch=30.0, roll=0.0)
        v = PointerMapper.cursor_velocity(rates=r, settings=s)
        self.assertLess(v.x, 0.0)
        self.assertLess(v.y, 0.0)

        s.invert_horizontal = True
        s.invert_vertical = True
        inv = PointerMapper.cursor_velocity(rates=r, settings=s)
        self.assertAlmostEqual(inv.x, -v.x, places=9)
        self.assertAlmostEqual(inv.y, -v.y, places=9)

    def test_differentiator_handles_wrap_around(self):
        d = MotionDifferentiator()
        self.assertIsNone(d.push(MotionSample(timestamp=0.0, yaw=math.pi - 0.01, pitch=0.0, roll=0.0)))
        r = d.push(MotionSample(timestamp=0.04, yaw=-math.pi + 0.01, pitch=0.0, roll=0.0))
        self.assertIsNotNone(r)
        # 0.02 rad over 0.04 s ≈ 28.6 deg/s, not a huge negative spin.
        expected_yaw = AngleMath.degrees(0.02) / 0.04
        self.assertAlmostEqual(r.yaw, expected_yaw, places=5)

    def test_differentiator_rejects_gaps(self):
        d = MotionDifferentiator()
        _ = d.push(MotionSample(timestamp=0.0, yaw=0.0, pitch=0.0, roll=0.0))
        self.assertIsNone(d.push(MotionSample(timestamp=1.0, yaw=1.0, pitch=0.0, roll=0.0)))
        self.assertIsNotNone(d.push(MotionSample(timestamp=1.04, yaw=1.01, pitch=0.0, roll=0.0)))

    def test_smoother_converges_and_stops_when_stale(self):
        s = PointerSmoother()
        s.set_target(Vec2(1000.0, 0.0), at=0.0)
        t = 0.0
        for _ in range(12):
            t += 1.0 / 120.0
            _ = s.step(now=t, dt=1.0 / 120.0, smoothing=0.5)
        self.assertAlmostEqual(s.velocity.x, 1000.0, delta=30.0)

        # No new samples -> decays to a full stop.
        for _ in range(120):
            t += 1.0 / 120.0
            _ = s.step(now=t, dt=1.0 / 120.0, smoothing=0.5)
        self.assertEqual(s.velocity, Vec2.zero)

    def test_smoother_zero_smoothing_is_immediate(self):
        s = PointerSmoother()
        s.set_target(Vec2(120.0, -60.0), at=0.0)
        delta = s.step(now=0.01, dt=0.01, smoothing=0.0)
        self.assertAlmostEqual(delta.x, 1.2, places=9)
        self.assertAlmostEqual(delta.y, -0.6, places=9)

    def test_cursor_history_lookup(self):
        h = CursorHistory(capacity=4)
        self.assertIsNone(h.position(at=1.0))
        for i in range(6):
            h.append(Vec2(float(i), 0.0), at=float(i))
        # Capacity 4 keeps t = 2...5.
        p_3_5 = h.position(at=3.5)
        self.assertIsNotNone(p_3_5)
        self.assertEqual(p_3_5.x, 3.0)

        p_100 = h.position(at=100.0)
        self.assertIsNotNone(p_100)
        self.assertEqual(p_100.x, 5.0)

        p_neg = h.position(at=-1.0)
        self.assertIsNotNone(p_neg)
        self.assertEqual(p_neg.x, 2.0)


class TestGestures(unittest.TestCase):
    """Corresponds to GestureTests.swift."""

    HZ = 25.0

    def feed(
        self,
        d: GestureDetector,
        pitch: list[float],
        yaw: list[float] | None = None,
        roll: list[float] | None = None,
        start: float = 0.0,
        enabled: set[HeadGesture] | None = None,
    ) -> list[GestureEvent]:
        out: list[GestureEvent] = []
        for i in range(len(pitch)):
            y = yaw[i] if yaw is not None else 0.0
            r = roll[i] if roll is not None else 0.0
            s = MotionSample(
                timestamp=start + float(i) / self.HZ,
                yaw=AngleMath.radians(y),
                pitch=AngleMath.radians(pitch[i]),
                roll=AngleMath.radians(r),
            )
            e = d.process(s, enabled=enabled)
            if e is not None:
                out.append(e)
        return out

    def dip(self, depth: float, over: float, lead: int = 5, tail: int = 8) -> list[float]:
        n = max(2, int(over * self.HZ))
        curve = [depth * math.sin(math.pi * float(i) / float(n)) for i in range(n + 1)]
        return [0.0] * lead + curve + [0.0] * tail

    def tilt_run(
        self, d: GestureDetector, rolls: list[float], start: float = 0.0
    ) -> list[GestureEvent]:
        return self.feed(d, pitch=[0.0] * len(rolls), roll=rolls, start=start)

    def test_natural_nod_detected(self):
        d = GestureDetector()
        events = self.feed(d, pitch=self.dip(-12.0, over=0.4))
        self.assertEqual([e.gesture for e in events], [HeadGesture.NOD])
        self.assertAlmostEqual(events[0].magnitude, 12.0, delta=1.0)
        # Starts at (or just before) the beginning of the dip, for cursor restore.
        self.assertLessEqual(events[0].start_time, 5.0 / self.HZ + 0.01)

    def test_gentle_nod_detected(self):
        d = GestureDetector()
        events = self.feed(d, pitch=self.dip(-7.0, over=0.5))
        self.assertEqual([e.gesture for e in events], [HeadGesture.NOD])

    def test_upward_nod_detected(self):
        d = GestureDetector()
        events = self.feed(d, pitch=self.dip(10.0, over=0.4))
        self.assertEqual([e.gesture for e in events], [HeadGesture.NOD])

    def test_tiny_jitter_is_not_a_nod(self):
        d = GestureDetector()
        events = self.feed(d, pitch=self.dip(-3.0, over=0.3))
        self.assertEqual(len(events), 0)

    def test_slow_look_down_and_back_is_not_a_nod(self):
        d = GestureDetector()
        events = self.feed(d, pitch=self.dip(-15.0, over=2.0))
        self.assertEqual(len(events), 0)

    def test_looking_down_and_staying_is_not_a_nod(self):
        d = GestureDetector()
        pitch = [0.0] * 5 + [-1.5 * float(i) for i in range(11)] + [-15.0] * 30
        self.assertEqual(len(self.feed(d, pitch=pitch)), 0)

    def test_diagonal_move_is_not_a_nod(self):
        d = GestureDetector()
        pitch = self.dip(-10.0, over=0.4)
        yaw = [float(i) * 1.5 for i in range(len(pitch))]  # sweeping sideways ~37 deg/s
        events = self.feed(d, pitch=pitch, yaw=yaw, enabled={HeadGesture.NOD})
        self.assertEqual(len(events), 0)

    def test_nod_with_rebound_fires_once(self):
        d = GestureDetector()
        nod = self.dip(-12.0, over=0.4, tail=0) + self.dip(6.0, over=0.3, lead=0)
        self.assertEqual(len(self.feed(d, pitch=nod)), 1)

    def test_nod_burst_without_settling_fires_once(self):
        d = GestureDetector()
        burst = (
            self.dip(-10.0, over=0.4, tail=0)
            + self.dip(-10.0, over=0.4, lead=0, tail=0)
            + self.dip(-10.0, over=0.4, lead=0)
        )
        self.assertEqual(len(self.feed(d, pitch=burst)), 1)

    def test_separate_nods_each_fire(self):
        d = GestureDetector()
        two = self.dip(-10.0, over=0.4, tail=15) + self.dip(-10.0, over=0.4, lead=0)
        events = self.feed(d, pitch=two)
        self.assertEqual([e.gesture for e in events], [HeadGesture.NOD, HeadGesture.NOD])

    def test_long_shake_fires_once(self):
        d = GestureDetector()
        n = int(2.0 * self.HZ)
        yaw = [14.0 * math.sin(2.0 * math.pi * float(i) / (0.45 * self.HZ)) for i in range(n + 1)] + [
            0.0
        ] * 10
        events = self.feed(d, pitch=[0.0] * len(yaw), yaw=yaw)
        self.assertEqual([e.gesture for e in events], [HeadGesture.SHAKE])

    def test_disabled_gestures_do_not_fire(self):
        d = GestureDetector()
        events = self.feed(d, pitch=self.dip(-12.0, over=0.4), enabled={HeadGesture.SHAKE})
        self.assertEqual(len(events), 0)

    def test_shake_detected(self):
        d = GestureDetector()
        n = int(1.1 * self.HZ)
        yaw = (
            [0.0] * 4
            + [15.0 * math.sin(2.0 * math.pi * float(i) / (0.5 * self.HZ)) for i in range(n + 1)]
            + [0.0] * 4
        )
        events = self.feed(d, pitch=[0.0] * len(yaw), yaw=yaw)
        self.assertEqual([e.gesture for e in events], [HeadGesture.SHAKE])

    def test_glancing_left_then_right_then_back_is_not_a_shake(self):
        d = GestureDetector()
        yaw = [0.0] * 4
        for i in range(7):
            yaw.append(-18.0 * float(i) / 6.0)
        for i in range(11):
            yaw.append(-18.0 + 36.0 * float(i) / 10.0)
        for i in range(7):
            yaw.append(18.0 - 18.0 * float(i) / 6.0)
        yaw += [0.0] * 6
        events = self.feed(d, pitch=[0.0] * len(yaw), yaw=yaw)
        self.assertEqual(len(events), 0)

    def test_single_look_aside_and_back_is_not_a_shake(self):
        d = GestureDetector()
        yaw = self.dip(-25.0, over=0.6)
        events = self.feed(d, pitch=[0.0] * len(yaw), yaw=yaw)
        self.assertEqual(len(events), 0)

    def test_yaw_wrap_around_is_continuous(self):
        d = GestureDetector()
        yaw = [179.0 if i % 2 == 0 else -179.0 for i in range(30)]
        events = self.feed(d, pitch=[0.0] * len(yaw), yaw=yaw)
        self.assertEqual(len(events), 0)

    def test_tilt_fires_once_after_hold(self):
        s = GestureSettings()
        s.tilt_angle = 20.0
        s.tilt_hold = 0.3
        d = GestureDetector(settings=s)
        events = self.tilt_run(d, rolls=[0.0] * 5 + [30.0] * 30)
        self.assertEqual([e.gesture for e in events], [HeadGesture.TILT_RIGHT])
        events += self.tilt_run(d, rolls=[0.0] * 5 + [-30.0] * 15, start=35.0 / self.HZ)
        self.assertEqual([e.gesture for e in events], [HeadGesture.TILT_RIGHT, HeadGesture.TILT_LEFT])

    def test_swap_tilt_direction(self):
        s = GestureSettings()
        s.swap_tilt_direction = True
        d = GestureDetector(settings=s)
        events = self.tilt_run(d, rolls=[0.0] + [30.0] * 20)
        self.assertEqual([e.gesture for e in events], [HeadGesture.TILT_LEFT])

    def test_brief_tilt_does_not_fire(self):
        d = GestureDetector()
        events = self.tilt_run(d, rolls=[0.0, 0.0, 30.0, 30.0, 0.0, 0.0])
        self.assertEqual(len(events), 0)

    def test_stale_neutral_recovers(self):
        d = GestureDetector()
        _ = self.tilt_run(d, rolls=[50.0])
        _ = self.tilt_run(d, rolls=[0.0] * 150, start=1.0 / self.HZ)
        self.assertAlmostEqual(d.relative_roll(0.0), 0.0, delta=1.0)
        events = self.tilt_run(d, rolls=[30.0] * 20, start=151.0 / self.HZ)
        self.assertEqual([e.gesture for e in events], [HeadGesture.TILT_RIGHT])


class TestDwell(unittest.TestCase):
    """Corresponds to DwellTests in GestureTests.swift."""

    def make_settings(self) -> DwellSettings:
        s = DwellSettings()
        s.enabled = True
        s.duration = 1.0
        s.radius = 10.0
        return s

    def test_fires_once_after_moving_then_resting(self):
        d = DwellDetector(settings=self.make_settings())
        _ = d.update(position=Vec2(0.0, 0.0), time=0.0)
        _ = d.update(position=Vec2(50.0, 0.0), time=0.1)  # movement arms it
        fires = 0
        t = 0.1
        while t < 4.0:
            t += 1.0 / 60.0
            if d.update(position=Vec2(52.0, 1.0), time=t).fired:
                fires += 1
        self.assertEqual(fires, 1)

    def test_does_not_fire_without_movement(self):
        d = DwellDetector(settings=self.make_settings())
        t = 0.0
        while t < 3.0:
            self.assertFalse(d.update(position=Vec2(5.0, 5.0), time=t).fired)
            t += 0.05

    def test_continuous_movement_never_fires(self):
        d = DwellDetector(settings=self.make_settings())
        t = 0.0
        x = 0.0
        while t < 3.0:
            self.assertFalse(d.update(position=Vec2(x, 0.0), time=t).fired)
            t += 0.05
            x += 15.0

    def test_anchor_id_changes_only_when_pointer_settles_somewhere_new(self):
        d = DwellDetector(settings=self.make_settings())
        _ = d.update(position=Vec2.zero, time=0.0)
        _ = d.update(position=Vec2(50.0, 0.0), time=0.1)
        first = d.anchor_id
        _ = d.update(position=Vec2(52.0, 2.0), time=0.2)
        self.assertEqual(d.anchor_id, first)
        _ = d.update(position=Vec2(120.0, 0.0), time=0.3)
        self.assertNotEqual(d.anchor_id, first)
        self.assertEqual(d.anchor_position, Vec2(120.0, 0.0))

    def test_progress_reveals_and_reset_disarms(self):
        d = DwellDetector(settings=self.make_settings())
        _ = d.update(position=Vec2.zero, time=0.0)
        _ = d.update(position=Vec2(40.0, 0.0), time=0.0)
        self.assertIsNone(d.update(position=Vec2(40.0, 0.0), time=0.1).progress)
        prog = d.update(position=Vec2(40.0, 0.0), time=0.5).progress
        self.assertIsNotNone(prog)
        self.assertAlmostEqual(prog, 0.5, places=9)
        d.reset()
        self.assertFalse(d.update(position=Vec2(40.0, 0.0), time=2.0).fired)


class TestSettings(unittest.TestCase):
    """Corresponds to SettingsTests in GestureTests.swift."""

    def test_round_trip(self):
        s = AppSettings()
        s.pointer.sensitivity = 2.5
        s.actions[Trigger.NOD] = PointerAction.DOUBLE_CLICK
        s.dwell.enabled = True
        json_str = s.to_json()
        decoded = AppSettings.from_json(json_str)
        self.assertEqual(decoded.pointer.sensitivity, s.pointer.sensitivity)
        self.assertEqual(decoded.actions[Trigger.NOD], PointerAction.DOUBLE_CLICK)
        self.assertEqual(decoded.dwell.enabled, s.dwell.enabled)

    def test_missing_and_unknown_keys_fall_back_to_defaults(self):
        json_str = (
            '{"pointer":{"sensitivity":3},"actions":{"nod":"rightClick","bogus":"leftClick",'
            '"shake":"notAnAction"},"futureKey":1}'
        )
        s = AppSettings.from_json(json_str)
        self.assertEqual(s.pointer.sensitivity, 3.0)
        self.assertEqual(s.pointer.deadzone, PointerSettings().deadzone)
        self.assertEqual(s.actions[Trigger.NOD], PointerAction.RIGHT_CLICK)
        self.assertEqual(s.actions[Trigger.SHAKE], ActionMap.DEFAULTS[Trigger.SHAKE])
        self.assertEqual(s.gestures, GestureSettings())

    def test_v1_settings_migrate_to_smart_hover_click(self):
        v1 = '{"dwell":{"enabled":false,"duration":1.0},"gestures":{"nodAmplitude":9},"pointer":{"sensitivity":2}}'
        s = AppSettings.from_json(v1).migrated()
        self.assertTrue(s.dwell.enabled)
        self.assertTrue(s.dwell.smart)
        self.assertEqual(s.gestures.nod_amplitude, GestureSettings().nod_amplitude)
        self.assertEqual(s.pointer.sensitivity, 2.0)  # unrelated choices survive
        self.assertEqual(s.version, AppSettings.CURRENT_VERSION)

    def test_v2_settings_get_deliberate_shake(self):
        v2 = '{"version":2,"gestures":{"shakeAmplitude":8,"shakeWindow":1.1},"dwell":{"enabled":false}}'
        s = AppSettings.from_json(v2).migrated()
        self.assertEqual(s.gestures.shake_amplitude, GestureSettings().shake_amplitude)
        self.assertFalse(s.dwell.enabled)  # a v2 user's own hover-click choice is kept

    def test_current_settings_are_not_re_migrated(self):
        s = AppSettings()
        s.dwell.enabled = False
        json_str = s.to_json()
        decoded = AppSettings.from_json(json_str).migrated()
        self.assertFalse(decoded.dwell.enabled)

    def test_action_map_queries(self):
        m = ActionMap()
        self.assertTrue(m.head_gesture_can_toggle_tracking)  # shake by default
        self.assertFalse(m.stem_can_toggle_tracking)
        m[Trigger.SHAKE] = PointerAction.NONE
        m[Trigger.NOD] = PointerAction.NONE
        self.assertFalse(m.head_gesture_can_toggle_tracking)
        self.assertNotIn(HeadGesture.NOD, m.enabled_head_gestures)
        m[Trigger.STEM_TRIPLE] = PointerAction.TOGGLE_TRACKING
        self.assertTrue(m.stem_can_toggle_tracking)


class TestUpdates(unittest.TestCase):
    """Corresponds to UpdateTests.swift."""

    PAGE_URL = "https://github.com/m-afham/AirCursor/releases/tag/v1.0.5"

    def make_release(self, tag: str, draft: bool = False, prerelease: bool = False) -> ReleaseInfo:
        return ReleaseInfo(tag_name=tag, html_url=self.PAGE_URL, draft=draft, prerelease=prerelease)

    def test_parses_versions_and_tags(self):
        v1 = AppVersion.parse("v1.0.4")
        self.assertIsNotNone(v1)
        self.assertEqual(v1.description, "1.0.4")

        v2 = AppVersion.parse("1.2")
        self.assertIsNotNone(v2)
        self.assertEqual(v2.description, "1.2.0")

        v3 = AppVersion.parse(" 2.0.1-beta.3 ")
        self.assertIsNotNone(v3)
        self.assertEqual(v3.description, "2.0.1")

        self.assertIsNone(AppVersion.parse(""))
        self.assertIsNone(AppVersion.parse("v"))
        self.assertIsNone(AppVersion.parse("1..2"))
        self.assertIsNone(AppVersion.parse("latest"))
        self.assertIsNone(AppVersion.parse("1.-2"))

    def test_compares_numerically_not_alphabetically(self):
        v = lambda s: AppVersion(s)
        self.assertLess(v("1.0.9"), v("1.0.10"))
        self.assertLess(v("1.9"), v("1.10"))
        self.assertLess(v("1.0.4"), v("2.0.0"))
        self.assertEqual(v("1.2"), v("1.2.0"))
        self.assertFalse(v("1.2.0") < v("1.2"))

    def test_offers_only_newer_final_releases(self):
        up = UpdatePolicy.update(
            current="1.0.4", release=self.make_release("v1.0.5"), skipped_version=None
        )
        self.assertIsNotNone(up)
        self.assertEqual(up.version.description, "1.0.5")

        self.assertIsNone(
            UpdatePolicy.update(
                current="1.0.4", release=self.make_release("v1.0.4"), skipped_version=None
            )
        )
        self.assertIsNone(
            UpdatePolicy.update(
                current="1.1.0", release=self.make_release("v1.0.9"), skipped_version=None
            )
        )
        self.assertIsNone(
            UpdatePolicy.update(
                current="1.0.4",
                release=self.make_release("v1.0.5", draft=True),
                skipped_version=None,
            )
        )
        self.assertIsNone(
            UpdatePolicy.update(
                current="1.0.4",
                release=self.make_release("v1.0.5", prerelease=True),
                skipped_version=None,
            )
        )
        self.assertIsNone(
            UpdatePolicy.update(
                current="dev", release=self.make_release("v1.0.5"), skipped_version=None
            )
        )
        self.assertIsNone(
            UpdatePolicy.update(
                current="1.0.4", release=self.make_release("nightly"), skipped_version=None
            )
        )

    def test_skipped_version_is_quiet_until_a_newer_one_or_a_manual_check(self):
        self.assertIsNone(
            UpdatePolicy.update(
                current="1.0.4",
                release=self.make_release("v1.0.5"),
                skipped_version="1.0.5",
            )
        )
        self.assertIsNotNone(
            UpdatePolicy.update(
                current="1.0.4",
                release=self.make_release("v1.0.5"),
                skipped_version="1.0.5",
                include_skipped=True,
            )
        )
        self.assertIsNotNone(
            UpdatePolicy.update(
                current="1.0.4",
                release=self.make_release("v1.0.6"),
                skipped_version="1.0.5",
            )
        )

    def test_check_is_due_once_per_interval(self):
        now = 1_000_000.0
        self.assertTrue(UpdatePolicy.is_check_due(last_check=None, now=now))
        self.assertFalse(UpdatePolicy.is_check_due(last_check=now - 3600, now=now))
        self.assertTrue(
            UpdatePolicy.is_check_due(last_check=now - UpdatePolicy.CHECK_INTERVAL, now=now)
        )
        self.assertTrue(
            UpdatePolicy.is_check_due(last_check=now + 3600, now=now),
            "a clock set back must not block checks",
        )

    def test_release_notes_become_plain_lines(self):
        body = """## What's Changed
* Give slow-starting AirPods time to stream motion (#5) by @m-afham in https://github.com/m-afham/AirCursor/pull/7
* Add update alerts by @dependabot[bot] in https://github.com/m-afham/AirCursor/pull/8

## New Contributors
- Better tilt thresholds

**Full Changelog**: https://github.com/m-afham/AirCursor/compare/v1.0.4...v1.0.5
"""
        self.assertEqual(
            ReleaseNotes.summary(body),
            [
                "Give slow-starting AirPods time to stream motion (#5)",
                "Add update alerts",
                "Better tilt thresholds",
            ],
        )
        self.assertEqual(len(ReleaseNotes.summary(body, max_lines=1)), 1)
        self.assertEqual(ReleaseNotes.summary(None), [])

    def test_finds_versioned_archive_and_signature(self):
        d = {
            "tag_name": "v1.0.5",
            "html_url": self.PAGE_URL,
            "assets": [
                {"name": "AirCursor.zip", "browser_download_url": "https://example.com/AirCursor.zip", "size": 10},
                {"name": "AirCursor-1.0.5.zip", "browser_download_url": "https://example.com/AirCursor-1.0.5.zip", "size": 10},
                {"name": "AirCursor-1.0.5.zip.sig", "browser_download_url": "https://example.com/AirCursor-1.0.5.zip.sig", "size": 89},
            ],
        }
        info = ReleaseInfo.from_dict(d)
        self.assertIsNotNone(info.archive)
        self.assertEqual(info.archive.name, "AirCursor-1.0.5.zip")
        self.assertIsNotNone(info.archive_signature)
        self.assertEqual(info.archive_signature.name, "AirCursor-1.0.5.zip.sig")
        self.assertEqual(info.archive.size, 10)

        unsigned = ReleaseInfo(
            tag_name="v1.0.4",
            html_url=self.PAGE_URL,
            assets=[ReleaseAsset(name="AirCursor-1.0.4.zip", url=self.PAGE_URL, size=1)],
        )
        self.assertIsNotNone(unsigned.archive)
        self.assertIsNone(unsigned.archive_signature)


if __name__ == "__main__":
    unittest.main()
