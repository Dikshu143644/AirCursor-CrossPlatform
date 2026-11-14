package io.github.aircursor

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.Service
import android.bluetooth.BluetoothAdapter
import android.bluetooth.BluetoothDevice
import android.bluetooth.BluetoothManager
import android.bluetooth.BluetoothSocket
import android.content.Context
import android.content.Intent
import android.hardware.Sensor
import android.hardware.SensorEvent
import android.hardware.SensorEventListener
import android.hardware.SensorManager
import android.os.Build
import android.os.IBinder
import android.util.Log
import androidx.core.app.NotificationCompat
import java.io.InputStream
import java.io.OutputStream
import java.lang.reflect.Method
import java.nio.ByteBuffer
import java.nio.ByteOrder
import java.util.UUID
import kotlin.concurrent.thread
import kotlin.math.*

/**
 * AirPods & Device IMU Motion Streaming Service.
 * Connects to paired AirPods via Bluetooth L2CAP socket (PSM 0x1001) with MTU 2582,
 * decodes RemoteHID & SensorDataWX 58-byte motion packets into head orientation,
 * and falls back seamlessly to phone's built-in IMU (Sensor.TYPE_ROTATION_VECTOR).
 */
class AirPodsMotionService : Service(), SensorEventListener {

    companion object {
        private const val TAG = "AirPodsMotionService"
        private const val CHANNEL_ID = "aircursor_motion_channel"
        private const val NOTIFICATION_ID = 1001

        const val ACTION_TELEMETRY = "io.github.aircursor.TELEMETRY"
        const val EXTRA_YAW = "extra_yaw"
        const val EXTRA_PITCH = "extra_pitch"
        const val EXTRA_ROLL = "extra_roll"
        const val EXTRA_STATUS = "extra_status"
        const val EXTRA_CONNECTED = "extra_connected"

        const val L2CAP_PSM_AAP = 0x1001
        const val AIRPODS_MTU = 2582

        var instance: AirPodsMotionService? = null
            private set
    }

    // Mathematical & interaction engine
    val settings = AppSettings()
    private val differentiator = MotionDifferentiator()
    private val smoother = PointerSmoother()
    private val gestureDetector = GestureDetector(settings.gestures)
    private val dwellDetector = DwellDetector(settings.dwell)
    private val history = CursorHistory(360)

    // State
    var isTrackingActive = true
    var isConnectedToAirPods = false
        private set

    // Bluetooth Worker
    private var btThread: Thread? = null
    private var isRunning = false
    private var btSocket: BluetoothSocket? = null

    // Fallback SensorManager
    private lateinit var sensorManager: SensorManager
    private var rotationSensor: Sensor? = null
    private var useFallbackImu = false

    override fun onCreate() {
        super.onCreate()
        instance = this
        sensorManager = getSystemService(Context.SENSOR_SERVICE) as SensorManager
        rotationSensor = sensorManager.getDefaultSensor(Sensor.TYPE_ROTATION_VECTOR)

        createNotificationChannel()
        startForeground(NOTIFICATION_ID, buildForegroundNotification("AirCursor Engine Active"))

        isRunning = true
        startBluetoothWorker()
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        return START_STICKY
    }

    override fun onDestroy() {
        super.onDestroy()
        instance = null
        isRunning = false
        stopBluetooth()
        stopFallbackImu()
    }

    override fun onBind(intent: Intent?): IBinder? = null

    // --------------------------------------------------------------------------
    // Foreground Notification
    // --------------------------------------------------------------------------

    private fun createNotificationChannel() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            val channel = NotificationChannel(
                CHANNEL_ID,
                "AirCursor Motion Engine",
                NotificationManager.IMPORTANCE_LOW
            ).apply {
                description = "Background motion tracking from AirPods and device sensors"
            }
            val manager = getSystemService(NotificationManager::class.java)
            manager.createNotificationChannel(channel)
        }
    }

    private fun buildForegroundNotification(contentText: String): Notification {
        return NotificationCompat.Builder(this, CHANNEL_ID)
            .setContentTitle("AirCursor")
            .setContentText(contentText)
            .setSmallIcon(android.R.drawable.ic_menu_compass)
            .setOngoing(true)
            .build()
    }

    // --------------------------------------------------------------------------
    // Bluetooth L2CAP Connection & RemoteHID Protocol
    // --------------------------------------------------------------------------

    private fun startBluetoothWorker() {
        btThread = thread(start = true, name = "AirPodsL2CAPWorker") {
            while (isRunning) {
                val device = findPairedAirPods()
                if (device == null) {
                    switchToFallbackImu("No paired AirPods found. Using Phone IMU.")
                    Thread.sleep(3000)
                    continue
                }

                broadcastStatus("Connecting to ${device.name}...", false)
                val socket = createL2capSocket(device, L2CAP_PSM_AAP)
                if (socket == null) {
                    switchToFallbackImu("L2CAP unavailable on device. Using Phone IMU.")
                    Thread.sleep(3000)
                    continue
                }

                try {
                    socket.connect()
                    btSocket = socket
                    isConnectedToAirPods = true
                    stopFallbackImu()
                    broadcastStatus("Connected to ${device.name}", true)

                    // Send activation handshake
                    sendStartHandshake(socket.outputStream)

                    val buffer = ByteArray(AIRPODS_MTU)
                    val inStream = socket.inputStream

                    while (isRunning && socket.isConnected) {
                        val bytesRead = inStream.read(buffer)
                        if (bytesRead <= 0) break
                        parseIncomingPacket(buffer, bytesRead)
                    }
                } catch (e: Exception) {
                    Log.w(TAG, "Bluetooth connection failed: ${e.message}")
                    switchToFallbackImu("AirPods disconnected. Using Phone IMU.")
                } finally {
                    try {
                        socket.close()
                    } catch (_: Exception) {}
                    btSocket = null
                    isConnectedToAirPods = false
                }
                Thread.sleep(2000)
            }
        }
    }

    private fun stopBluetooth() {
        try {
            btSocket?.close()
        } catch (_: Exception) {}
        btSocket = null
        btThread?.interrupt()
    }

    private fun findPairedAirPods(): BluetoothDevice? {
        val btManager = getSystemService(Context.BLUETOOTH_SERVICE) as? BluetoothManager ?: return null
        val adapter = btManager.adapter ?: return null
        if (!adapter.isEnabled) return null

        try {
            val bonded = adapter.bondedDevices ?: return null
            for (dev in bonded) {
                val name = dev.name?.lowercase() ?: ""
                if (name.contains("airpod") || name.contains("beats")) {
                    return dev
                }
            }
        } catch (e: SecurityException) {
            Log.w(TAG, "Missing BLUETOOTH_CONNECT permission")
        }
        return null
    }

    /**
     * Creates an L2CAP socket using API 29+ createL2capChannel or reflection fallback.
     */
    private fun createL2capSocket(device: BluetoothDevice, psm: Int): BluetoothSocket? {
        return try {
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
                device.createInsecureL2capChannel(psm)
            } else {
                val m: Method = device.javaClass.getMethod("createInsecureL2capSocket", Int::class.javaPrimitiveType)
                m.invoke(device, psm) as BluetoothSocket
            }
        } catch (e: Exception) {
            // RFCOMM fallback (Standard Serial Port UUID)
            try {
                val uuid = UUID.fromString("00001101-0000-1000-8000-00805F9B34FB")
                device.createRfcommSocketToServiceRecord(uuid)
            } catch (_: Exception) {
                null
            }
        }
    }

    private fun sendStartHandshake(outStream: OutputStream) {
        try {
            // Feature report 1 with interval 10000us (100Hz)
            val devmotionSubpacket = byteArrayOf(
                0x87.toByte(), 0x04, 0x06, 0x00, // Header: devID=7, len=9, kind=3 (SetReport)
                0x01,                             // Report ID 1
                0x10, 0x27, 0x00, 0x00           // 10000 us (100 Hz)
            )
            // AACP frame with RTBuddy opcode 0x17 and descriptor 0x800
            val body = byteArrayOf(0x00, 0x01, 0x00, 0x00) + devmotionSubpacket
            val rtBuddyHeader = ByteBuffer.allocate(8).order(ByteOrder.LITTLE_ENDIAN).apply {
                putShort(0x0017)
                putInt(0x00000800)
                putShort(body.size.toShort())
            }.array()
            val packet = byteArrayOf(0xFF.toByte(), 0x55) + rtBuddyHeader + body
            outStream.write(packet)
            outStream.flush()
        } catch (_: Exception) {}
    }

    private fun parseIncomingPacket(data: ByteArray, length: Int) {
        if (length < 26) return

        // Scan for 58-byte motion block (or parse directly if aligned)
        var offset = 0
        if (length >= 4 && data[0] == 0xFF.toByte() && data[1] == 0x55.toByte()) {
            offset = 12 // Skip AACP + RTBuddy header
        }

        if (offset + 26 <= length) {
            val bb = ByteBuffer.wrap(data, offset, length - offset).order(ByteOrder.LITTLE_ENDIAN)
            val rawX = bb.getShort(20)
            val rawY = bb.getShort(22)
            val rawZ = bb.getShort(24)

            val x = rawX / 32768.0
            val y = rawY / 32768.0
            val z = rawZ / 32768.0
            val w = sqrt(max(0.0, 1.0 - (x * x + y * y + z * z)))

            val yaw = atan2(2.0 * (w * z + x * y), 1.0 - 2.0 * (y * y + z * z))
            val pitch = asin((2.0 * (w * y - z * x)).coerceIn(-1.0, 1.0))
            val roll = atan2(2.0 * (w * x + y * z), 1.0 - 2.0 * (x * x + y * y))

            val sample = MotionSample(System.currentTimeMillis() / 1000.0, yaw, pitch, roll)
            onMotionSample(sample)
        }
    }

    // --------------------------------------------------------------------------
    // Phone Fallback IMU (Sensor.TYPE_ROTATION_VECTOR)
    // --------------------------------------------------------------------------

    private fun switchToFallbackImu(reason: String) {
        if (useFallbackImu) return
        useFallbackImu = true
        broadcastStatus(reason, false)
        rotationSensor?.let {
            sensorManager.registerListener(this, it, SensorManager.SENSOR_DELAY_GAME)
        }
    }

    private fun stopFallbackImu() {
        if (!useFallbackImu) return
        useFallbackImu = false
        sensorManager.unregisterListener(this)
    }

    override fun onSensorChanged(event: SensorEvent?) {
        if (event == null || event.sensor.type != Sensor.TYPE_ROTATION_VECTOR) return

        val rotMatrix = FloatArray(9)
        SensorManager.getRotationMatrixFromVector(rotMatrix, event.values)
        val orientations = FloatArray(3)
        SensorManager.getOrientation(rotMatrix, orientations)

        // orientations: [0] = yaw (azimuth), [1] = pitch, [2] = roll
        val sample = MotionSample(
            timestamp = event.timestamp / 1_000_000_000.0,
            yaw = orientations[0].toDouble(),
            pitch = orientations[1].toDouble(),
            roll = orientations[2].toDouble()
        )
        onMotionSample(sample)
    }

    override fun onAccuracyChanged(sensor: Sensor?, accuracy: Int) {}

    // --------------------------------------------------------------------------
    // Motion Processing & Gesture Execution
    // --------------------------------------------------------------------------

    private fun onMotionSample(sample: MotionSample) {
        val now = sample.timestamp
        broadcastTelemetry(sample.yaw, sample.pitch, sample.roll)

        val rates = differentiator.push(sample) ?: return

        // 1. Gesture Detection
        val gestureEvent = gestureDetector.process(sample, settings.actions.enabledHeadGestures)
        if (gestureEvent != null) {
            handleGesture(gestureEvent)
        }

        // 2. Pointer Movement
        if (isTrackingActive) {
            val targetVel = PointerMapper.cursorVelocity(rates, settings.pointer)
            smoother.setTarget(targetVel, now)

            val dt = 0.01 // Approximate step interval
            val disp = smoother.step(now, dt, settings.pointer.smoothing)

            val a11y = AirCursorAccessibilityService.instance
            if (disp.x != 0.0 || disp.y != 0.0) {
                a11y?.moveRelative(disp.x.toFloat(), disp.y.toFloat())
            }

            // 3. Dwell Hover Click
            val curPos = Vec2(a11y?.curX?.toDouble() ?: 540.0, a11y?.curY?.toDouble() ?: 1200.0)
            history.append(curPos, now)

            if (settings.dwell.enabled) {
                val dwellUpdate = dwellDetector.update(curPos, now)
                DwellOverlayService.instance?.updateDwellProgress(dwellUpdate.progress)

                if (dwellUpdate.fired) {
                    val isClickable = a11y?.isInteractiveAt() ?: true
                    if (isClickable || !settings.dwell.smart) {
                        a11y?.dispatchClick()
                    }
                }
            }
        }
    }

    private fun handleGesture(event: GestureEvent) {
        val action = settings.actions.get(Trigger(event.gesture))
        val a11y = AirCursorAccessibilityService.instance

        when (action) {
            PointerAction.LEFT_CLICK -> {
                // Restore pre-nod cursor position
                val preNodPos = history.positionAt(event.startTime)
                if (preNodPos != null && a11y != null) {
                    a11y.moveRelative((preNodPos.x - a11y.curX).toFloat(), (preNodPos.y - a11y.curY).toFloat())
                }
                a11y?.dispatchClick()
            }
            PointerAction.RIGHT_CLICK -> a11y?.dispatchClick()
            PointerAction.DOUBLE_CLICK -> a11y?.dispatchDoubleClick()
            PointerAction.TOGGLE_TRACKING -> {
                isTrackingActive = !isTrackingActive
                smoother.reset()
            }
            PointerAction.RECENTER -> {
                a11y?.recenter()
                smoother.reset()
            }
            PointerAction.BACK -> a11y?.actionBack()
            PointerAction.HOME -> a11y?.actionHome()
            PointerAction.RECENTS -> a11y?.actionRecents()
            else -> {}
        }
    }

    // --------------------------------------------------------------------------
    // Telemetry Broadcasts
    // --------------------------------------------------------------------------

    private fun broadcastTelemetry(yaw: Double, pitch: Double, roll: Double) {
        val intent = Intent(ACTION_TELEMETRY).apply {
            putExtra(EXTRA_YAW, AngleMath.degrees(yaw))
            putExtra(EXTRA_PITCH, AngleMath.degrees(pitch))
            putExtra(EXTRA_ROLL, AngleMath.degrees(roll))
        }
        sendBroadcast(intent)
    }

    private fun broadcastStatus(status: String, connected: Boolean) {
        val intent = Intent(ACTION_TELEMETRY).apply {
            putExtra(EXTRA_STATUS, status)
            putExtra(EXTRA_CONNECTED, connected)
        }
        sendBroadcast(intent)
    }
}
