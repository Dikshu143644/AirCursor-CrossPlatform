package io.github.aircursor

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.os.SystemClock
import android.util.Log
import android.view.KeyEvent

/**
 * AirPods Stem Press Broadcast Receiver.
 * Intercepts ACTION_MEDIA_BUTTON broadcasts triggered by physical squeeze/presses on AirPods stems:
 * - 1 press  (Play/Pause or Headset Hook) -> Stem Single (Default: Left Click)
 * - 2 presses (Next Track)                -> Stem Double (Default: Right Click)
 * - 3 presses (Previous Track)            -> Stem Triple (Default: Scroll Mode Toggle)
 */
class StemReceiver : BroadcastReceiver() {

    companion object {
        private const val TAG = "StemReceiver"
        private const val DEBOUNCE_MS = 250L
        private var lastPressTime = 0L
    }

    override fun onReceive(context: Context, intent: Intent) {
        if (Intent.ACTION_MEDIA_BUTTON != intent.action) return

        @Suppress("DEPRECATION")
        val keyEvent = intent.getParcelableExtra<KeyEvent>(Intent.EXTRA_KEY_EVENT) ?: return
        if (keyEvent.action != KeyEvent.ACTION_DOWN) return

        val now = SystemClock.uptimeMillis()
        if (now - lastPressTime < DEBOUNCE_MS) {
            // Filter double-event deliveries (e.g. key down + repeated media broadcast)
            return
        }
        lastPressTime = now

        val a11y = AirCursorAccessibilityService.instance
        val motionService = AirPodsMotionService.instance
        val actionMap = motionService?.settings?.actions ?: ActionMap()

        Log.d(TAG, "AirPods stem press detected (KeyCode: ${keyEvent.keyCode})")

        when (keyEvent.keyCode) {
            KeyEvent.KEYCODE_MEDIA_PLAY_PAUSE,
            KeyEvent.KEYCODE_HEADSETHOOK,
            KeyEvent.KEYCODE_MEDIA_PLAY,
            KeyEvent.KEYCODE_MEDIA_PAUSE -> {
                val action = actionMap.get(Trigger.STEM_SINGLE)
                executeAction(action, a11y)
                abortBroadcast()
            }
            KeyEvent.KEYCODE_MEDIA_NEXT -> {
                val action = actionMap.get(Trigger.STEM_DOUBLE)
                executeAction(action, a11y)
                abortBroadcast()
            }
            KeyEvent.KEYCODE_MEDIA_PREVIOUS -> {
                val action = actionMap.get(Trigger.STEM_TRIPLE)
                executeAction(action, a11y)
                abortBroadcast()
            }
        }
    }

    private fun executeAction(action: PointerAction, a11y: AirCursorAccessibilityService?) {
        when (action) {
            PointerAction.LEFT_CLICK -> a11y?.dispatchClick()
            PointerAction.RIGHT_CLICK -> a11y?.dispatchClick()
            PointerAction.DOUBLE_CLICK -> a11y?.dispatchDoubleClick()
            PointerAction.TOGGLE_TRACKING -> {
                AirPodsMotionService.instance?.let {
                    it.isTrackingActive = !it.isTrackingActive
                }
            }
            PointerAction.RECENTER -> a11y?.recenter()
            PointerAction.BACK -> a11y?.actionBack()
            PointerAction.HOME -> a11y?.actionHome()
            PointerAction.RECENTS -> a11y?.actionRecents()
            else -> {}
        }
    }
}
