package io.github.aircursor

import android.app.Service
import android.content.Context
import android.content.Intent
import android.graphics.Canvas
import android.graphics.Paint
import android.graphics.PixelFormat
import android.graphics.RectF
import android.os.Build
import android.os.Handler
import android.os.IBinder
import android.os.Looper
import android.view.Gravity
import android.view.View
import android.view.WindowManager
import androidx.core.content.ContextCompat

/**
 * System Overlay Service.
 * Uses WindowManager with TYPE_APPLICATION_OVERLAY to render a transparent,
 * click-through circular dwell progress bar and touch ripple pulse around the pointer.
 */
class DwellOverlayService : Service() {

    companion object {
        var instance: DwellOverlayService? = null
            private set
    }

    private lateinit var windowManager: WindowManager
    private lateinit var overlayView: CursorOverlayView
    private lateinit var layoutParams: WindowManager.LayoutParams
    private val mainHandler = Handler(Looper.getMainLooper())

    private val overlaySizeDp = 72
    private var overlaySizePx = 216

    override fun onCreate() {
        super.onCreate()
        instance = this
        windowManager = getSystemService(Context.WINDOW_SERVICE) as WindowManager

        val density = resources.displayMetrics.density
        overlaySizePx = (overlaySizeDp * density).toInt()

        val layoutType = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            WindowManager.LayoutParams.TYPE_APPLICATION_OVERLAY
        } else {
            @Suppress("DEPRECATION")
            WindowManager.LayoutParams.TYPE_PHONE
        }

        layoutParams = WindowManager.LayoutParams(
            overlaySizePx,
            overlaySizePx,
            layoutType,
            WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE or
                    WindowManager.LayoutParams.FLAG_NOT_TOUCHABLE or
                    WindowManager.LayoutParams.FLAG_LAYOUT_NO_LIMITS or
                    WindowManager.LayoutParams.FLAG_HARDWARE_ACCELERATED,
            PixelFormat.TRANSLUCENT
        ).apply {
            gravity = Gravity.TOP or Gravity.START
            x = 400
            y = 800
        }

        overlayView = CursorOverlayView(this)
        try {
            windowManager.addView(overlayView, layoutParams)
        } catch (_: Exception) {}
    }

    override fun onDestroy() {
        super.onDestroy()
        instance = null
        try {
            windowManager.removeView(overlayView)
        } catch (_: Exception) {}
    }

    override fun onBind(intent: Intent?): IBinder? = null

    // --------------------------------------------------------------------------
    // Public API for Cursor Updates
    // --------------------------------------------------------------------------

    fun updatePosition(x: Float, y: Float) {
        mainHandler.post {
            layoutParams.x = (x - overlaySizePx / 2f).toInt()
            layoutParams.y = (y - overlaySizePx / 2f).toInt()
            try {
                windowManager.updateViewLayout(overlayView, layoutParams)
            } catch (_: Exception) {}
        }
    }

    fun updateDwellProgress(progress: Double?) {
        mainHandler.post {
            overlayView.dwellProgress = progress?.toFloat()
            overlayView.invalidate()
        }
    }

    fun triggerPulse(x: Float, y: Float) {
        mainHandler.post {
            updatePosition(x, y)
            overlayView.startPulse()
        }
    }

    // --------------------------------------------------------------------------
    // Custom Canvas Overlay View
    // --------------------------------------------------------------------------

    private class CursorOverlayView(context: Context) : View(context) {
        var dwellProgress: Float? = null

        private var pulseActive = false
        private var pulseStartTime = 0L
        private val pulseDuration = 350L

        private val centerDotPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
            color = ContextCompat.getColor(context, R.color.primary)
            style = Paint.Style.FILL
        }

        private val centerDotBorderPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
            color = 0xFFFFFFFF.toInt()
            style = Paint.Style.STROKE
            strokeWidth = 3f
        }

        private val trackPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
            color = ContextCompat.getColor(context, R.color.cursor_track)
            style = Paint.Style.STROKE
            strokeWidth = 8f
        }

        private val ringPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
            color = ContextCompat.getColor(context, R.color.cursor_ring)
            style = Paint.Style.STROKE
            strokeWidth = 8f
            strokeCap = Paint.Cap.ROUND
        }

        private val pulsePaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
            color = ContextCompat.getColor(context, R.color.cursor_pulse)
            style = Paint.Style.STROKE
            strokeWidth = 6f
        }

        private val ringRect = RectF()

        fun startPulse() {
            pulseActive = true
            pulseStartTime = System.currentTimeMillis()
            invalidate()
        }

        override fun onDraw(canvas: Canvas) {
            super.onDraw(canvas)
            val cx = width / 2f
            val cy = height / 2f
            val radius = (minOf(width, height) / 2f) - 16f

            // 1. Center Cursor Dot
            canvas.drawCircle(cx, cy, 6f, centerDotPaint)
            canvas.drawCircle(cx, cy, 6f, centerDotBorderPaint)

            // 2. Click Ripple Pulse
            if (pulseActive) {
                val elapsed = System.currentTimeMillis() - pulseStartTime
                if (elapsed < pulseDuration) {
                    val frac = elapsed.toFloat() / pulseDuration
                    val pRadius = radius * (0.4f + 1.2f * frac)
                    pulsePaint.alpha = ((1f - frac) * 180).toInt().coerceIn(0, 255)
                    canvas.drawCircle(cx, cy, pRadius, pulsePaint)
                    postInvalidateOnAnimation()
                } else {
                    pulseActive = false
                }
            }

            // 3. Circular Dwell Progress Arc
            val prog = dwellProgress
            if (prog != null && prog > 0f) {
                ringRect.set(cx - radius, cy - radius, cx + radius, cy + radius)
                // Draw background track
                canvas.drawArc(ringRect, 0f, 360f, false, trackPaint)
                // Draw progress arc starting at 12 o'clock (-90 degrees)
                val sweepAngle = (prog.coerceIn(0f, 1f) * 360f)
                canvas.drawArc(ringRect, -90f, sweepAngle, false, ringPaint)
            }
        }
    }
}
