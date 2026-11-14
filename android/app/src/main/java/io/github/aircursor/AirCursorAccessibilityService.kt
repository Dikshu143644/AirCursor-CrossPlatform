package io.github.aircursor

import android.accessibilityservice.AccessibilityService
import android.accessibilityservice.GestureDescription
import android.content.Intent
import android.graphics.Path
import android.graphics.Rect
import android.os.Handler
import android.os.Looper
import android.util.DisplayMetrics
import android.util.Log
import android.view.accessibility.AccessibilityEvent
import android.view.accessibility.AccessibilityNodeInfo

/**
 * AirCursor Accessibility Service.
 * Uses dispatchGesture() with Path to synthesize taps, double-clicks, drags, and scrolls
 * anywhere on Android without requiring root access.
 * Inspects node hierarchy for smart dwell clicking.
 */
class AirCursorAccessibilityService : AccessibilityService() {

    companion object {
        private const val TAG = "AirCursorA11y"
        var instance: AirCursorAccessibilityService? = null
            private set
    }

    private val mainHandler = Handler(Looper.getMainLooper())
    var screenWidth: Int = 1080
        private set
    var screenHeight: Int = 2400
        private set

    var curX: Float = 540f
        private set
    var curY: Float = 1200f
        private set

    override fun onServiceConnected() {
        super.onServiceConnected()
        instance = this
        val metrics: DisplayMetrics = resources.displayMetrics
        screenWidth = metrics.widthPixels
        screenHeight = metrics.heightPixels
        curX = screenWidth / 2f
        curY = screenHeight / 2f
        Log.i(TAG, "AirCursor Accessibility Service connected (Display: ${screenWidth}x${screenHeight})")

        // Start overlay service
        startService(Intent(this, DwellOverlayService::class.java))
    }

    override fun onAccessibilityEvent(event: AccessibilityEvent?) {
        // Can monitor window state changes or active apps if needed
    }

    override fun onInterrupt() {
        Log.w(TAG, "AirCursor Accessibility Service interrupted")
    }

    override fun onDestroy() {
        super.onDestroy()
        instance = null
        Log.i(TAG, "AirCursor Accessibility Service destroyed")
    }

    // --------------------------------------------------------------------------
    // Cursor Movement & Coordinate Updates
    // --------------------------------------------------------------------------

    fun moveRelative(dx: Float, dy: Float) {
        curX = (curX + dx).coerceIn(0f, screenWidth.toFloat())
        curY = (curY + dy).coerceIn(0f, screenHeight.toFloat())

        // Notify overlay to update its drawn position
        DwellOverlayService.instance?.updatePosition(curX, curY)
    }

    fun recenter() {
        curX = screenWidth / 2f
        curY = screenHeight / 2f
        DwellOverlayService.instance?.updatePosition(curX, curY)
    }

    // --------------------------------------------------------------------------
    // Gesture Dispatch (Clicks, Taps, Scrolls)
    // --------------------------------------------------------------------------

    /**
     * Dispatches a single tap at coordinates (x, y) using AccessibilityService.dispatchGesture.
     */
    fun dispatchClick(x: Float = curX, y: Float = curY, onComplete: (() -> Unit)? = null) {
        val clickPath = Path().apply {
            moveTo(x, y)
        }
        val stroke = GestureDescription.StrokeDescription(clickPath, 0, 50)
        val gesture = GestureDescription.Builder().addStroke(stroke).build()

        dispatchGesture(gesture, object : GestureResultCallback() {
            override fun onCompleted(gestureDescription: GestureDescription?) {
                DwellOverlayService.instance?.triggerPulse(x, y)
                onComplete?.invoke()
            }
            override fun onCancelled(gestureDescription: GestureDescription?) {
                Log.w(TAG, "Click gesture cancelled at ($x, $y)")
            }
        }, mainHandler)
    }

    /**
     * Dispatches a double-click gesture at coordinates (x, y).
     */
    fun dispatchDoubleClick(x: Float = curX, y: Float = curY) {
        dispatchClick(x, y) {
            mainHandler.postDelayed({
                dispatchClick(x, y)
            }, 60)
        }
    }

    /**
     * Dispatches a scroll/swipe gesture starting from (x, y).
     */
    fun dispatchScroll(dx: Float, dy: Float, x: Float = curX, y: Float = curY) {
        val path = Path().apply {
            moveTo(x, y)
            lineTo(x + dx, y + dy)
        }
        val stroke = GestureDescription.StrokeDescription(path, 0, 150)
        val gesture = GestureDescription.Builder().addStroke(stroke).build()
        dispatchGesture(gesture, null, mainHandler)
    }

    // --------------------------------------------------------------------------
    // Smart Interactive Node Probing
    // --------------------------------------------------------------------------

    /**
     * Checks if the element under (x, y) is an interactive control (button, link, field).
     */
    fun isInteractiveAt(x: Float = curX, y: Float = curY): Boolean {
        val root = rootInActiveWindow ?: return true // Fallback to clickable if window tree unavailable
        val ix = x.toInt()
        val iy = y.toInt()

        return findInteractiveNode(root, ix, iy)
    }

    private fun findInteractiveNode(node: AccessibilityNodeInfo, x: Int, y: Int): Boolean {
        val rect = Rect()
        node.getBoundsInScreen(rect)
        if (!rect.contains(x, y)) {
            return false
        }

        // If this node is explicitly clickable, checkable, editable or focusable
        if (node.isClickable || node.isCheckable || node.isEditable) {
            // Check compact size heuristic (prevent full-screen background views from claiming clicks)
            val width = rect.width()
            val height = rect.height()
            if (width <= screenWidth * 0.95 && height <= screenHeight * 0.40) {
                return true
            }
        }

        // Recurse children
        for (i in 0 until node.childCount) {
            val child = node.getChild(i) ?: continue
            if (findInteractiveNode(child, x, y)) {
                return true
            }
        }
        return false
    }

    // --------------------------------------------------------------------------
    // System Navigation Actions
    // --------------------------------------------------------------------------

    fun actionBack() = performGlobalAction(GLOBAL_ACTION_BACK)
    fun actionHome() = performGlobalAction(GLOBAL_ACTION_HOME)
    fun actionRecents() = performGlobalAction(GLOBAL_ACTION_RECENTS)
}
