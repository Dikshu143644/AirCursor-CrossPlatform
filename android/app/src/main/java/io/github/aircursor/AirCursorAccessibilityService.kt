package io.github.aircursor

import android.accessibilityservice.AccessibilityService
import android.accessibilityservice.GestureDescription
import android.content.Context
import android.content.Intent
import android.graphics.Path
import android.graphics.Rect
import android.net.wifi.WifiManager
import android.os.Handler
import android.os.Looper
import android.util.DisplayMetrics
import android.util.Log
import android.view.accessibility.AccessibilityEvent
import android.view.accessibility.AccessibilityNodeInfo
import okhttp3.*
import org.json.JSONObject
import java.net.DatagramPacket
import java.net.DatagramSocket
import java.net.InetAddress
import java.net.NetworkInterface
import java.util.concurrent.TimeUnit
import kotlin.concurrent.thread

/**
 * AirCursor Accessibility Service with Full WebSocket Client & Automatic UDP Discovery.
 * 
 * 1. Automatic UDP Discovery on port 4242:
 *    Broadcasts discovery probes across all active network interfaces and listens for server responses.
 * 2. Full WebSocket Client:
 *    Connects to ws://<host>:8765/ws (or http://<host>:8765/ws) with auto-reconnection.
 * 3. Bidirectional Control:
 *    Receives remote clicks, pointer movements, and scroll gestures from the host,
 *    and streams local sensor attitude/telemetry upstream.
 * 4. Gesture Dispatcher:
 *    Uses AccessibilityService.dispatchGesture() with Path to tap, double-click, and drag without root.
 */
class AirCursorAccessibilityService : AccessibilityService() {

    companion object {
        private const val TAG = "AirCursorA11y"
        const val UDP_DISCOVERY_PORT = 4242
        const val DEFAULT_HTTP_PORT = 8765
        const val ACTION_SERVER_STATUS = "io.github.aircursor.SERVER_STATUS"
        const val EXTRA_SERVER_HOST = "extra_server_host"
        const val EXTRA_CONNECTED = "extra_connected"

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

    // Networking components
    private var udpDiscoveryThread: Thread? = null
    private var isDiscovering = false
    private var discoveredHost: String? = null
    private var okHttpClient: OkHttpClient? = null
    private var webSocket: WebSocket? = null
    private var isWebSocketConnected = false
    private var multicastLock: WifiManager.MulticastLock? = null

    override fun onServiceConnected() {
        super.onServiceConnected()
        instance = this
        val metrics: DisplayMetrics = resources.displayMetrics
        screenWidth = metrics.widthPixels
        screenHeight = metrics.heightPixels
        curX = screenWidth / 2f
        curY = screenHeight / 2f
        Log.i(TAG, "AirCursor Accessibility Service connected (${screenWidth}x${screenHeight})")

        // Start overlay service
        try {
            startService(Intent(this, DwellOverlayService::class.java))
        } catch (e: Exception) {
            Log.w(TAG, "Could not start overlay service: ${e.message}")
        }

        // Start Automatic UDP Discovery on port 4242 & WebSocket connection
        acquireMulticastLock()
        startUdpDiscovery()
    }

    override fun onAccessibilityEvent(event: AccessibilityEvent?) {}

    override fun onInterrupt() {
        Log.w(TAG, "Accessibility Service interrupted")
    }

    override fun onDestroy() {
        super.onDestroy()
        instance = null
        stopUdpDiscovery()
        disconnectWebSocket()
        releaseMulticastLock()
        Log.i(TAG, "Accessibility Service destroyed")
    }

    // --------------------------------------------------------------------------
    // Automatic UDP Discovery (Port 4242)
    // --------------------------------------------------------------------------

    private fun acquireMulticastLock() {
        try {
            val wifi = applicationContext.getSystemService(Context.WIFI_SERVICE) as? WifiManager
            multicastLock = wifi?.createMulticastLock("AirCursorUDP")?.apply {
                setReferenceCounted(true)
                acquire()
            }
        } catch (_: Exception) {}
    }

    private fun releaseMulticastLock() {
        try {
            if (multicastLock?.isHeld == true) {
                multicastLock?.release()
            }
        } catch (_: Exception) {}
    }

    private fun startUdpDiscovery() {
        if (isDiscovering) return
        isDiscovering = true

        udpDiscoveryThread = thread(start = true, name = "AirCursor-UdpDiscovery") {
            Log.i(TAG, "[UDP] Starting automatic server discovery on port $UDP_DISCOVERY_PORT...")
            var socket: DatagramSocket? = null

            try {
                socket = DatagramSocket(null).apply {
                    reuseAddress = true
                    broadcast = true
                    soTimeout = 2500
                    bind(java.net.InetSocketAddress(0)) // Ephemeral local port to avoid collisions
                }

                val probePayload = JSONObject().apply {
                    put("type", "discover")
                    put("service", "aircursor_android")
                    put("client", "accessibility_companion")
                    put("port", UDP_DISCOVERY_PORT)
                }.toString().toByteArray(Charsets.UTF_8)

                val buffer = ByteArray(1024)
                var attempts = 0

                while (isDiscovering && !isWebSocketConnected) {
                    attempts++
                    // 1. Send broadcast probes to 255.255.255.255 and all interface broadcast addresses
                    try {
                        val packet255 = DatagramPacket(
                            probePayload,
                            probePayload.size,
                            InetAddress.getByName("255.255.255.255"),
                            UDP_DISCOVERY_PORT
                        )
                        socket.send(packet255)

                        // Probe interface broadcast addresses
                        val interfaces = NetworkInterface.getNetworkInterfaces()
                        while (interfaces.hasMoreElements()) {
                            val iface = interfaces.nextElement()
                            if (!iface.isUp || iface.isLoopback) continue
                            for (addr in iface.interfaceAddresses) {
                                val bcast = addr.broadcast
                                if (bcast != null) {
                                    val pkt = DatagramPacket(probePayload, probePayload.size, bcast, UDP_DISCOVERY_PORT)
                                    socket.send(pkt)
                                }
                            }
                        }
                    } catch (e: Exception) {
                        Log.d(TAG, "[UDP] Broadcast send notice: ${e.message}")
                    }

                    // 2. Listen for incoming server announcements or responses
                    try {
                        val recvPacket = DatagramPacket(buffer, buffer.size)
                        socket.receive(recvPacket)

                        val respText = String(recvPacket.data, 0, recvPacket.length, Charsets.UTF_8).trim()
                        val senderHost = recvPacket.address.hostAddress ?: ""
                        Log.i(TAG, "[UDP] Received packet from $senderHost: $respText")

                        var targetPort = DEFAULT_HTTP_PORT
                        if (respText.startsWith("{")) {
                            try {
                                val json = JSONObject(respText)
                                targetPort = json.optInt("http_port", DEFAULT_HTTP_PORT)
                            } catch (_: Exception) {}
                        }

                        if (senderHost.isNotEmpty()) {
                            discoveredHost = senderHost
                            Log.i(TAG, "[UDP] Discovered AirCursor Server at $senderHost:$targetPort")
                            connectWebSocket(senderHost, targetPort)
                        }
                    } catch (e: java.net.SocketTimeoutException) {
                        // Periodic retry
                    } catch (e: Exception) {
                        Log.d(TAG, "[UDP] Socket read: ${e.message}")
                    }

                    // Wait between discovery bursts
                    Thread.sleep(if (isWebSocketConnected) 5000 else 2000)
                }
            } catch (e: Exception) {
                Log.w(TAG, "[UDP] Discovery error: ${e.message}")
            } finally {
                socket?.close()
            }
        }
    }

    private fun stopUdpDiscovery() {
        isDiscovering = false
        udpDiscoveryThread?.interrupt()
        udpDiscoveryThread = null
    }

    // --------------------------------------------------------------------------
    // WebSocket Client Connectivity (http://<host>:8765/ws)
    // --------------------------------------------------------------------------

    /**
     * Connects to ws://<host>:8765/ws with auto-reconnection and command processing.
     */
    fun connectWebSocket(host: String, port: Int = DEFAULT_HTTP_PORT) {
        if (isWebSocketConnected && discoveredHost == host) return

        disconnectWebSocket()
        discoveredHost = host

        if (okHttpClient == null) {
            okHttpClient = OkHttpClient.Builder()
                .readTimeout(0, TimeUnit.MILLISECONDS)
                .pingInterval(10, TimeUnit.SECONDS)
                .retryOnConnectionFailure(true)
                .build()
        }

        val wsUrl = "ws://$host:$port/ws"
        Log.i(TAG, "[WebSocket] Connecting to $wsUrl...")

        val request = Request.Builder()
            .url(wsUrl)
            .build()

        webSocket = okHttpClient?.newWebSocket(request, object : WebSocketListener() {
            override fun onOpen(webSocket: WebSocket, response: Response) {
                isWebSocketConnected = true
                Log.i(TAG, "[WebSocket] Connected successfully to $wsUrl")
                broadcastServerStatus(host, true)

                // Send client handshake
                val hello = JSONObject().apply {
                    put("type", "client_hello")
                    put("client", "android_accessibility")
                    put("screen_width", screenWidth)
                    put("screen_height", screenHeight)
                    put("cursor_x", curX)
                    put("cursor_y", curY)
                }
                webSocket.send(hello.toString())
            }

            override fun onMessage(webSocket: WebSocket, text: String) {
                handleIncomingWebSocketMessage(text)
            }

            override fun onClosing(webSocket: WebSocket, code: Int, reason: String) {
                Log.i(TAG, "[WebSocket] Closing: $code / $reason")
                webSocket.close(1000, null)
            }

            override fun onClosed(webSocket: WebSocket, code: Int, reason: String) {
                isWebSocketConnected = false
                Log.w(TAG, "[WebSocket] Closed: $code / $reason")
                broadcastServerStatus(host, false)
                scheduleReconnect()
            }

            override fun onFailure(webSocket: WebSocket, t: Throwable, response: Response?) {
                isWebSocketConnected = false
                Log.w(TAG, "[WebSocket] Connection failure: ${t.message}")
                broadcastServerStatus(host, false)
                scheduleReconnect()
            }
        })
    }

    fun disconnectWebSocket() {
        try {
            webSocket?.close(1000, "Service destroyed")
        } catch (_: Exception) {}
        webSocket = null
        isWebSocketConnected = false
    }

    private fun scheduleReconnect() {
        if (!isDiscovering) return
        mainHandler.postDelayed({
            val host = discoveredHost
            if (!isWebSocketConnected && host != null) {
                Log.i(TAG, "[WebSocket] Attempting auto-reconnect to $host...")
                connectWebSocket(host, DEFAULT_HTTP_PORT)
            }
        }, 3000)
    }

    private fun handleIncomingWebSocketMessage(jsonText: String) {
        try {
            val json = JSONObject(jsonText)
            val action = json.optString("action", json.optString("type", "")).lowercase()

            when (action) {
                "click", "left_click" -> {
                    val x = json.optDouble("x", curX.toDouble()).toFloat()
                    val y = json.optDouble("y", curY.toDouble()).toFloat()
                    mainHandler.post { dispatchClick(x, y) }
                }
                "double_click" -> {
                    val x = json.optDouble("x", curX.toDouble()).toFloat()
                    val y = json.optDouble("y", curY.toDouble()).toFloat()
                    mainHandler.post { dispatchDoubleClick(x, y) }
                }
                "move" -> {
                    val dx = json.optDouble("dx", 0.0).toFloat()
                    val dy = json.optDouble("dy", 0.0).toFloat()
                    mainHandler.post { moveRelative(dx, dy) }
                }
                "move_to" -> {
                    val x = json.optDouble("x", curX.toDouble()).toFloat()
                    val y = json.optDouble("y", curY.toDouble()).toFloat()
                    mainHandler.post {
                        curX = x.coerceIn(0f, screenWidth.toFloat())
                        curY = y.coerceIn(0f, screenHeight.toFloat())
                        DwellOverlayService.instance?.updatePosition(curX, curY)
                    }
                }
                "scroll" -> {
                    val dx = json.optDouble("dx", 0.0).toFloat()
                    val dy = json.optDouble("dy", 0.0).toFloat()
                    mainHandler.post { dispatchScroll(dx, dy) }
                }
                "recenter" -> {
                    mainHandler.post { recenter() }
                }
                "back" -> mainHandler.post { actionBack() }
                "home" -> mainHandler.post { actionHome() }
                "recents" -> mainHandler.post { actionRecents() }
                "ping" -> {
                    webSocket?.send(JSONObject().put("type", "pong").toString())
                }
            }
        } catch (e: Exception) {
            Log.w(TAG, "[WebSocket] Parse error: ${e.message}")
        }
    }

    fun sendTelemetry(yaw: Double, pitch: Double, roll: Double) {
        if (!isWebSocketConnected) return
        try {
            val msg = JSONObject().apply {
                put("type", "telemetry")
                put("yaw", yaw)
                put("pitch", pitch)
                put("roll", roll)
            }
            webSocket?.send(msg.toString())
        } catch (_: Exception) {}
    }

    private fun broadcastServerStatus(host: String, connected: Boolean) {
        val intent = Intent(ACTION_SERVER_STATUS).apply {
            putExtra(EXTRA_SERVER_HOST, host)
            putExtra(EXTRA_CONNECTED, connected)
        }
        sendBroadcast(intent)
    }

    // --------------------------------------------------------------------------
    // Cursor Movement & Coordinate Updates
    // --------------------------------------------------------------------------

    fun moveRelative(dx: Float, dy: Float) {
        curX = (curX + dx).coerceIn(0f, screenWidth.toFloat())
        curY = (curY + dy).coerceIn(0f, screenHeight.toFloat())

        // Notify overlay to update drawn position
        DwellOverlayService.instance?.updatePosition(curX, curY)

        // Send position update upstream if connected
        if (isWebSocketConnected && (dx != 0f || dy != 0f)) {
            try {
                val pos = JSONObject().apply {
                    put("type", "cursor_position")
                    put("x", curX)
                    put("y", curY)
                }
                webSocket?.send(pos.toString())
            } catch (_: Exception) {}
        }
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

    fun isInteractiveAt(x: Float = curX, y: Float = curY): Boolean {
        val root = rootInActiveWindow ?: return true
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

        if (node.isClickable || node.isCheckable || node.isEditable) {
            val width = rect.width()
            val height = rect.height()
            if (width <= screenWidth * 0.95 && height <= screenHeight * 0.40) {
                return true
            }
        }

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
