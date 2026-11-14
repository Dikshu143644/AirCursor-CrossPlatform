package io.github.aircursor

import org.junit.Assert.*
import org.junit.Test

class AirCursorCoreTest {

    @Test
    fun testVec2Operations() {
        val v1 = Vec2(3.0, 4.0)
        assertEquals(5.0, v1.length, 1e-4)

        val v2 = Vec2(1.0, 2.0)
        val v3 = v1 + v2
        assertEquals(4.0, v3.x, 1e-4)
        assertEquals(6.0, v3.y, 1e-4)

        val dist = v1.distance(Vec2(0.0, 0.0))
        assertEquals(5.0, dist, 1e-4)
    }

    @Test
    fun testAngleMathWrapping() {
        // 179° - (-179°) = 358° -> wraps to -2°
        val radA = AngleMath.radians(179.0)
        val radB = AngleMath.radians(-179.0)
        val wrappedRad = AngleMath.wrappedDelta(radA, radB)
        val wrappedDeg = AngleMath.degrees(wrappedRad)
        assertEquals(-2.0, wrappedDeg, 1e-3)

        val directDeg = AngleMath.wrappedDeltaDegrees(179.0, -179.0)
        assertEquals(-2.0, directDeg, 1e-3)
    }

    @Test
    fun testMotionDifferentiator() {
        val diff = MotionDifferentiator()
        val t0 = 100.0
        assertNull(diff.push(MotionSample(t0, 0.0, 0.0, 0.0)))

        val t1 = t0 + 0.01
        val sample1 = MotionSample(t1, 0.1, 0.0, 0.0)
        val rates = diff.push(sample1)
        assertNotNull(rates)
        val expectedYawRate = AngleMath.degrees(0.1) / 0.01
        assertEquals(expectedYawRate, rates!!.yaw, 1e-2)
    }

    @Test
    fun testMotionDifferentiatorGapRejection() {
        val diff = MotionDifferentiator()
        diff.push(MotionSample(10.0, 0.0, 0.0, 0.0))
        // 0.5s gap (> MAX_INTERVAL 0.25s) -> should be rejected
        val rates = diff.push(MotionSample(10.5, 0.5, 0.0, 0.0))
        assertNull(rates)
    }

    @Test
    fun testPointerMapperDeadzone() {
        val settings = PointerSettings(deadzone = 3.0, sensitivity = 1.0)
        assertEquals(0.0, PointerMapper.axisSpeed(2.5, settings), 1e-4)
        assertEquals(0.0, PointerMapper.axisSpeed(-2.9, settings), 1e-4)

        val speed = PointerMapper.axisSpeed(4.0, settings)
        assertTrue(speed > 0.0)
    }

    @Test
    fun testPointerSmoother() {
        val smoother = PointerSmoother()
        smoother.setTarget(Vec2(100.0, 0.0), 10.0)
        val disp = smoother.step(10.01, 0.01, 0.55)
        assertTrue(disp.x > 0.0)
    }

    @Test
    fun testNodDetection() {
        val detector = GestureDetector(GestureSettings(nodAmplitude = 5.0, nodWindow = 0.8))
        var t = 1.0
        val pitches = doubleArrayOf(0.0, -2.0, -5.0, -7.0, -4.0, -1.0, 0.0)
        var detectedEvent: GestureEvent? = null

        for (p in pitches) {
            val sample = MotionSample(
                timestamp = t,
                yaw = 0.0,
                pitch = AngleMath.radians(p),
                roll = 0.0
            )
            val e = detector.process(sample, setOf(HeadGesture.NOD))
            if (e != null) {
                detectedEvent = e
                break
            }
            t += 0.04
        }

        assertNotNull(detectedEvent)
        assertEquals(HeadGesture.NOD, detectedEvent!!.gesture)
        assertTrue(detectedEvent.magnitude >= 5.0)
    }

    @Test
    fun testDwellDetector() {
        val detector = DwellDetector(DwellSettings(duration = 0.5, radius = 10.0))
        val pos = Vec2(100.0, 200.0)
        var t = 1.0

        val u0 = detector.update(pos, t)
        assertFalse(u0.fired)
        assertNull(u0.progress)

        // Move slightly to arm
        val posDrift = Vec2(115.0, 200.0)
        t += 0.1
        val u1 = detector.update(posDrift, t)
        assertTrue(detector.isArmed)

        // Rest for 0.3s (progress >= revealFraction)
        t += 0.3
        val u2 = detector.update(posDrift, t)
        assertFalse(u2.fired)
        assertNotNull(u2.progress)

        // Rest until 0.5s duration elapsed
        t += 0.3
        val u3 = detector.update(posDrift, t)
        assertTrue(u3.fired)
        assertEquals(1.0, u3.progress!!, 1e-4)
    }

    @Test
    fun testActionMapDefaults() {
        val map = ActionMap()
        assertEquals(PointerAction.LEFT_CLICK, map.get(Trigger.STEM_SINGLE))
        assertEquals(PointerAction.RIGHT_CLICK, map.get(Trigger.STEM_DOUBLE))
        assertEquals(PointerAction.TOGGLE_SCROLL_MODE, map.get(Trigger.STEM_TRIPLE))
        assertEquals(PointerAction.LEFT_CLICK, map.get(Trigger.NOD))
        assertEquals(PointerAction.TOGGLE_TRACKING, map.get(Trigger.SHAKE))
        assertEquals(PointerAction.LEFT_CLICK, map.get(Trigger.DWELL))
    }
}
