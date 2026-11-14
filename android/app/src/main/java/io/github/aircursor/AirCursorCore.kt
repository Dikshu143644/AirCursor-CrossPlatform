package io.github.aircursor

import kotlin.math.*

// ==============================================================================
// Math Primitives & Angles
// ==============================================================================

data class Vec2(var x: Double = 0.0, var y: Double = 0.0) {
    val length: Double get() = hypot(x, y)

    fun distance(other: Vec2): Double = hypot(x - other.x, y - other.y)

    operator fun plus(other: Vec2) = Vec2(x + other.x, y + other.y)
    operator fun minus(other: Vec2) = Vec2(x - other.x, y - other.y)
    operator fun times(scalar: Double) = Vec2(x * scalar, y * scalar)

    companion object {
        val ZERO = Vec2(0.0, 0.0)
    }
}

object AngleMath {
    /** Shortest signed difference `a - b` in radians, wrapped into (-π, π]. */
    fun wrappedDelta(a: Double, b: Double): Double = atan2(sin(a - b), cos(a - b))

    /** Shortest signed difference `a - b` in degrees, wrapped into (-180, 180]. */
    fun wrappedDeltaDegrees(a: Double, b: Double): Double =
        degrees(wrappedDelta(radians(a), radians(b)))

    fun degrees(rad: Double): Double = rad * 180.0 / PI
    fun radians(deg: Double): Double = deg * PI / 180.0
}

// ==============================================================================
// Motion Readings & Differentiation
// ==============================================================================

data class MotionSample(
    val timestamp: Double, // in seconds
    val yaw: Double,       // radians
    val pitch: Double,     // radians
    val roll: Double       // radians
)

data class AngularRates(
    val timestamp: Double,
    val yaw: Double,       // deg/s
    val pitch: Double,     // deg/s
    val roll: Double       // deg/s
)

class MotionDifferentiator {
    private var last: MotionSample? = null

    companion object {
        const val MIN_INTERVAL = 0.002
        const val MAX_INTERVAL = 0.25
    }

    fun reset() {
        last = null
    }

    fun push(sample: MotionSample): AngularRates? {
        val previous = last
        last = sample
        if (previous == null) return null

        val dt = sample.timestamp - previous.timestamp
        if (dt < MIN_INTERVAL || dt > MAX_INTERVAL) return null

        return AngularRates(
            timestamp = sample.timestamp,
            yaw = AngleMath.degrees(AngleMath.wrappedDelta(sample.yaw, previous.yaw)) / dt,
            pitch = AngleMath.degrees(AngleMath.wrappedDelta(sample.pitch, previous.pitch)) / dt,
            roll = AngleMath.degrees(AngleMath.wrappedDelta(sample.roll, previous.roll)) / dt
        )
    }
}

// ==============================================================================
// Pointer Velocity Mapping & Smoothing
// ==============================================================================

data class PointerSettings(
    var sensitivity: Double = 1.0,
    var acceleration: Double = 0.6,
    var deadzone: Double = 3.0,       // deg/s
    var smoothing: Double = 0.55,
    var invertHorizontal: Boolean = false,
    var invertVertical: Boolean = false,
    var scrollSpeed: Double = 1.0,
    var invertScroll: Boolean = false
)

object PointerMapper {
    const val PIXELS_PER_DEGREE = 28.0

    fun axisSpeed(rate: Double, settings: PointerSettings): Double {
        val magnitude = abs(rate)
        if (magnitude <= settings.deadzone) return 0.0
        val effective = magnitude - settings.deadzone
        val boost = 1.0 + settings.acceleration * min(effective / 60.0, 3.0)
        val speed = effective * PIXELS_PER_DEGREE * settings.sensitivity * boost
        return if (rate < 0) -speed else speed
    }

    fun cursorVelocity(rates: AngularRates, settings: PointerSettings): Vec2 {
        var dx = -axisSpeed(rates.yaw, settings)
        var dy = -axisSpeed(rates.pitch, settings)
        if (settings.invertHorizontal) dx = -dx
        if (settings.invertVertical) dy = -dy
        return Vec2(dx, dy)
    }
}

class PointerSmoother {
    var velocity: Vec2 = Vec2.ZERO
        private set

    private var target: Vec2 = Vec2.ZERO
    private var targetTime: Double = Double.NEGATIVE_INFINITY

    companion object {
        const val STALE_AFTER = 0.12
    }

    fun setTarget(v: Vec2, timestamp: Double) {
        target = v
        targetTime = timestamp
    }

    fun reset() {
        velocity = Vec2.ZERO
        target = Vec2.ZERO
        targetTime = Double.NEGATIVE_INFINITY
    }

    fun step(now: Double, dt: Double, smoothing: Double): Vec2 {
        if (dt <= 0.0) return Vec2.ZERO
        val goal = if ((now - targetTime) > STALE_AFTER) Vec2.ZERO else target
        val s = min(max(smoothing, 0.0), 0.97)
        val alpha = 1.0 - s.pow(dt * 60.0)
        velocity = Vec2(
            velocity.x + (goal.x - velocity.x) * alpha,
            velocity.y + (goal.y - velocity.y) * alpha
        )
        if (goal == Vec2.ZERO && velocity.length < 2.0) {
            velocity = Vec2.ZERO
        }
        return velocity * dt
    }
}

class CursorHistory(val capacity: Int = 360) {
    private val buffer = ArrayList<Pair<Double, Vec2>>(max(1, capacity))
    private var head = 0

    fun append(position: Vec2, timestamp: Double) {
        val entry = Pair(timestamp, Vec2(position.x, position.y))
        if (buffer.size < capacity) {
            buffer.add(entry)
        } else {
            buffer[head] = entry
            head = (head + 1) % capacity
        }
    }

    fun clear() {
        buffer.clear()
        head = 0
    }

    fun positionAt(timestamp: Double): Vec2? {
        if (buffer.isEmpty()) return null
        val ordered = if (buffer.size < capacity) {
            buffer
        } else {
            buffer.subList(head, buffer.size) + buffer.subList(0, head)
        }
        var best = ordered[0].second
        for (item in ordered) {
            if (item.first <= timestamp) best = item.second else break
        }
        return Vec2(best.x, best.y)
    }
}

// ==============================================================================
// Gestures & Detection
// ==============================================================================

enum class HeadGesture(val value: String) {
    NOD("nod"),
    SHAKE("shake"),
    TILT_LEFT("tiltLeft"),
    TILT_RIGHT("tiltRight")
}

data class GestureEvent(
    val gesture: HeadGesture,
    val startTime: Double,
    val time: Double,
    val magnitude: Double
)

data class GestureSettings(
    var nodAmplitude: Double = 5.5,
    var nodWindow: Double = 0.8,
    var shakeAmplitude: Double = 12.0,
    var shakeWindow: Double = 1.4,
    var tiltAngle: Double = 22.0,
    var tiltHold: Double = 0.3,
    var swapTiltDirection: Boolean = false,
    var cooldown: Double = 0.5
)

class GestureDetector(var settings: GestureSettings = GestureSettings()) {
    private data class Pose(val t: Double, val yaw: Double, val pitch: Double)

    private val history = mutableListOf<Pose>()
    private var lastRawYaw: Double? = null
    private var cooldownUntil = Double.NEGATIVE_INFINITY
    private var awaitingStill = false
    private var stillSince: Double? = null
    private var rollBaseline: Double? = null
    private var tiltCandidate: Pair<HeadGesture, Double>? = null
    private var tiltLatched = false
    private var offNeutralSince: Double? = null

    companion object {
        const val RE_NEUTRAL_AFTER = 4.0
        const val NOD_RETURN_FRACTION = 0.65
        const val CROSS_AXIS_ALLOWANCE = 0.6
        const val MIN_NOD_SPEED = 30.0
        const val MIN_SHAKE_SPEED = 80.0
        const val SHAKE_SWINGS = 4
        const val HISTORY_SPAN = 1.5
        const val SETTLED_SPEED = 25.0
        const val SETTLED_FOR = 0.15
    }

    fun relativeRoll(rollDegrees: Double): Double {
        val base = rollBaseline ?: return 0.0
        return AngleMath.wrappedDeltaDegrees(rollDegrees, base)
    }

    fun resetTiltBaseline(rollDegrees: Double? = null) {
        rollBaseline = rollDegrees
        offNeutralSince = null
        tiltCandidate = null
        tiltLatched = false
    }

    fun reset() {
        history.clear()
        lastRawYaw = null
        cooldownUntil = Double.NEGATIVE_INFINITY
        awaitingStill = false
        stillSince = null
        resetTiltBaseline()
    }

    fun process(sample: MotionSample, enabled: Set<HeadGesture>): GestureEvent? {
        val t = sample.timestamp
        val rawYaw = AngleMath.degrees(sample.yaw)
        val pitch = AngleMath.degrees(sample.pitch)
        val roll = AngleMath.degrees(sample.roll)

        if (history.isNotEmpty() && (t - history.last().t > MotionDifferentiator.MAX_INTERVAL || t <= history.last().t)) {
            history.clear()
            lastRawYaw = null
        }

        val yaw = if (lastRawYaw != null && history.isNotEmpty()) {
            history.last().yaw + AngleMath.wrappedDeltaDegrees(rawYaw, lastRawYaw!!)
        } else {
            rawYaw
        }
        lastRawYaw = rawYaw

        history.add(Pose(t, yaw, pitch))
        while (history.isNotEmpty() && t - history.first().t > HISTORY_SPAN) {
            history.removeAt(0)
        }

        val tilt = updateTilt(roll, t, enabled)

        if (awaitingStill) {
            val speed = if (history.size >= 2) peakSpeedBetween(history[history.size - 2], history.last()) else 0.0
            if (speed < SETTLED_SPEED) {
                if (stillSince == null) stillSince = t
                if (t - stillSince!! >= SETTLED_FOR) {
                    awaitingStill = false
                    stillSince = null
                    val lastPose = history.last()
                    history.clear()
                    history.add(lastPose)
                }
            } else {
                stillSince = null
            }
            return null
        }

        if (t < cooldownUntil) return null

        if (HeadGesture.NOD in enabled) {
            val e = detectNod(t)
            if (e != null) return fire(e)
        }

        if (HeadGesture.SHAKE in enabled) {
            val e = detectShake(t)
            if (e != null) return fire(e)
        }

        if (tilt != null) return fire(tilt)

        return null
    }

    private fun fire(event: GestureEvent): GestureEvent {
        cooldownUntil = event.time + settings.cooldown
        awaitingStill = true
        stillSince = null
        tiltCandidate = null
        return event
    }

    private fun peakSpeedBetween(a: Pose, b: Pose): Double {
        if (b.t <= a.t) return 0.0
        return max(abs(b.pitch - a.pitch), abs(b.yaw - a.yaw)) / (b.t - a.t)
    }

    private fun detectNod(now: Double): GestureEvent? {
        if (history.size < 3) return null
        val current = history.last()
        val lastIndex = history.size - 1

        for (j in 0 until (lastIndex - 1)) {
            if (now - history[j].t > settings.nodWindow) continue
            val start = history[j]
            var extreme = 0.0
            var extremeIndex = j

            for (k in (j + 1) until lastIndex) {
                val d = history[k].pitch - start.pitch
                if (abs(d) > abs(extreme)) {
                    extreme = d
                    extremeIndex = k
                }
            }

            val depth = abs(extreme)
            if (depth < settings.nodAmplitude || extremeIndex <= j) continue

            val remaining = abs(current.pitch - start.pitch)
            if (remaining > depth * (1.0 - NOD_RETURN_FRACTION)) continue

            val segment = history.subList(j, lastIndex + 1)
            val yawRange = segment.maxOf { it.yaw } - segment.minOf { it.yaw }
            if (yawRange > max(depth * CROSS_AXIS_ALLOWANCE, 3.0)) continue
            if (peakSpeed(segment) { it.pitch } < MIN_NOD_SPEED) continue

            return GestureEvent(HeadGesture.NOD, start.t, now, depth)
        }
        return null
    }

    private fun detectShake(now: Double): GestureEvent? {
        val window = history.filter { now - it.t <= settings.shakeWindow }
        if (window.size < 4) return null

        var anchor = window.first().yaw
        var direction = 0
        var swings = 0
        var largest = 0.0

        for (pose in window.drop(1)) {
            val d = pose.yaw - anchor
            when (direction) {
                0 -> if (abs(d) >= settings.shakeAmplitude) {
                    direction = if (d > 0) 1 else -1
                    swings = 1
                    largest = abs(d)
                    anchor = pose.yaw
                }
                1 -> if (pose.yaw > anchor) {
                    anchor = pose.yaw
                } else if (anchor - pose.yaw >= settings.shakeAmplitude) {
                    swings++
                    largest = max(largest, anchor - pose.yaw)
                    direction = -1
                    anchor = pose.yaw
                }
                else -> if (pose.yaw < anchor) {
                    anchor = pose.yaw
                } else if (pose.yaw - anchor >= settings.shakeAmplitude) {
                    swings++
                    largest = max(largest, pose.yaw - anchor)
                    direction = 1
                    anchor = pose.yaw
                }
            }
        }

        if (swings < SHAKE_SWINGS) return null

        val pitchRange = window.maxOf { it.pitch } - window.minOf { it.pitch }
        if (pitchRange > largest * CROSS_AXIS_ALLOWANCE) return null
        if (peakSpeed(window) { it.yaw } < MIN_SHAKE_SPEED) return null

        return GestureEvent(HeadGesture.SHAKE, window.first().t, now, largest)
    }

    private fun peakSpeed(poses: List<Pose>, axis: (Pose) -> Double): Double {
        var best = 0.0
        for (i in 1 until poses.size) {
            val dt = poses[i].t - poses[i - 1].t
            if (dt > 0.0) {
                val rate = abs(axis(poses[i]) - axis(poses[i - 1])) / dt
                if (rate > best) best = rate
            }
        }
        return best
    }

    private fun updateTilt(rollDegrees: Double, t: Double, enabled: Set<HeadGesture>): GestureEvent? {
        val base = rollBaseline ?: run {
            rollBaseline = rollDegrees
            return null
        }

        val rel = AngleMath.wrappedDeltaDegrees(rollDegrees, base)

        if (abs(rel) < settings.tiltAngle * 0.5) {
            rollBaseline = base + rel * 0.02
            tiltLatched = false
            tiltCandidate = null
            offNeutralSince = null
            return null
        }

        if (offNeutralSince != null) {
            if (t - offNeutralSince!! > RE_NEUTRAL_AFTER) {
                rollBaseline = rollDegrees
                offNeutralSince = null
                tiltCandidate = null
                tiltLatched = false
                return null
            }
        } else {
            offNeutralSince = t
        }

        if ((HeadGesture.TILT_LEFT !in enabled && HeadGesture.TILT_RIGHT !in enabled) || tiltLatched) return null
        if (abs(rel) < settings.tiltAngle) {
            tiltCandidate = null
            return null
        }

        val isRight = (rel > 0) != settings.swapTiltDirection
        val gesture = if (isRight) HeadGesture.TILT_RIGHT else HeadGesture.TILT_LEFT

        val cand = tiltCandidate
        if (cand == null || cand.first != gesture) {
            tiltCandidate = Pair(gesture, t)
            return null
        }

        if (t - cand.second < settings.tiltHold) return null

        tiltLatched = true
        val candSince = cand.second
        tiltCandidate = null

        if (gesture in enabled && t >= cooldownUntil) {
            return GestureEvent(gesture, candSince, t, abs(rel))
        }
        return null
    }
}

// ==============================================================================
// Dwell Detection
// ==============================================================================

data class DwellSettings(
    var enabled: Boolean = true,
    var smart: Boolean = true,
    var duration: Double = 0.8,
    var radius: Double = 16.0
)

data class DwellUpdate(val progress: Double?, val fired: Boolean)

class DwellDetector(var settings: DwellSettings = DwellSettings()) {
    private var anchor: Vec2? = null
    private var anchorTime: Double = 0.0
    var isArmed: Boolean = false
        private set
    var anchorId: Int = 0
        private set

    companion object {
        const val REVEAL_FRACTION = 0.2
    }

    fun reset() {
        isArmed = false
        anchor = null
    }

    fun update(position: Vec2, timestamp: Double): DwellUpdate {
        val a = anchor ?: run {
            anchor = Vec2(position.x, position.y)
            anchorTime = timestamp
            return DwellUpdate(progress = null, fired = false)
        }

        if (position.distance(a) > settings.radius) {
            anchor = Vec2(position.x, position.y)
            anchorTime = timestamp
            isArmed = true
            anchorId++
            return DwellUpdate(progress = null, fired = false)
        }

        if (!isArmed || settings.duration <= 0.0) return DwellUpdate(progress = null, fired = false)

        val fraction = (timestamp - anchorTime) / settings.duration
        if (fraction >= 1.0) {
            isArmed = false
            return DwellUpdate(progress = 1.0, fired = true)
        }

        val prog = if (fraction >= REVEAL_FRACTION) fraction else null
        return DwellUpdate(progress = prog, fired = false)
    }
}

// ==============================================================================
// Triggers & Actions
// ==============================================================================

enum class Trigger(val value: String) {
    STEM_SINGLE("stemSingle"),
    STEM_DOUBLE("stemDouble"),
    STEM_TRIPLE("stemTriple"),
    NOD("nod"),
    SHAKE("shake"),
    TILT_LEFT("tiltLeft"),
    TILT_RIGHT("tiltRight"),
    DWELL("dwell");

    val isStem: Boolean get() = this == STEM_SINGLE || this == STEM_DOUBLE || this == STEM_TRIPLE

    val headGesture: HeadGesture?
        get() = when (this) {
            NOD -> HeadGesture.NOD
            SHAKE -> HeadGesture.SHAKE
            TILT_LEFT -> HeadGesture.TILT_LEFT
            TILT_RIGHT -> HeadGesture.TILT_RIGHT
            else -> null
        }
}

enum class PointerAction(val value: String) {
    NONE("none"),
    LEFT_CLICK("leftClick"),
    RIGHT_CLICK("rightClick"),
    DOUBLE_CLICK("doubleClick"),
    MIDDLE_CLICK("middleClick"),
    TOGGLE_DRAG("toggleDrag"),
    TOGGLE_SCROLL_MODE("toggleScrollMode"),
    TOGGLE_TRACKING("toggleTracking"),
    RECENTER("recenter"),
    BACK("back"),
    HOME("home"),
    RECENTS("recents");

    val isClick: Boolean
        get() = this == LEFT_CLICK || this == RIGHT_CLICK || this == DOUBLE_CLICK || this == MIDDLE_CLICK || this == TOGGLE_DRAG
}

class ActionMap {
    private val bindings = mutableMapOf<Trigger, PointerAction>()

    init {
        bindings[Trigger.STEM_SINGLE] = PointerAction.LEFT_CLICK
        bindings[Trigger.STEM_DOUBLE] = PointerAction.RIGHT_CLICK
        bindings[Trigger.STEM_TRIPLE] = PointerAction.TOGGLE_SCROLL_MODE
        bindings[Trigger.NOD] = PointerAction.LEFT_CLICK
        bindings[Trigger.SHAKE] = PointerAction.TOGGLE_TRACKING
        bindings[Trigger.TILT_LEFT] = PointerAction.NONE
        bindings[Trigger.TILT_RIGHT] = PointerAction.NONE
        bindings[Trigger.DWELL] = PointerAction.LEFT_CLICK
    }

    fun get(trigger: Trigger): PointerAction = bindings[trigger] ?: PointerAction.NONE

    fun set(trigger: Trigger, action: PointerAction) {
        bindings[trigger] = action
    }

    val enabledHeadGestures: Set<HeadGesture>
        get() = Trigger.values().mapNotNull { t ->
            t.headGesture?.takeIf { get(t) != PointerAction.NONE }
        }.toSet()
}

data class AppSettings(
    var pointer: PointerSettings = PointerSettings(),
    var gestures: GestureSettings = GestureSettings(),
    var dwell: DwellSettings = DwellSettings(),
    var actions: ActionMap = ActionMap(),
    var stemControlsEnabled: Boolean = true,
    var showOverlay: Boolean = true
)
