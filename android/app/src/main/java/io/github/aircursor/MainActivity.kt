package io.github.aircursor

import android.Manifest
import android.accessibilityservice.AccessibilityServiceInfo
import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.content.IntentFilter
import android.content.pm.PackageManager
import android.net.Uri
import android.os.Build
import android.os.Bundle
import android.provider.Settings
import android.view.accessibility.AccessibilityManager
import android.widget.Button
import android.widget.TextView
import android.widget.Toast
import androidx.appcompat.app.AppCompatActivity
import androidx.core.app.ActivityCompat
import androidx.core.content.ContextCompat
import com.google.android.material.materialswitch.MaterialSwitch
import com.google.android.material.slider.Slider

/**
 * AirCursor Setup, Calibration & Tuning Activity.
 * Guides user through required permissions (Accessibility, Overlay, Bluetooth),
 * controls sensitivity & dwell sliders, and displays live orientation telemetry.
 */
class MainActivity : AppCompatActivity() {

    private lateinit var switchService: MaterialSwitch
    private lateinit var btnAccessibility: Button
    private lateinit var btnOverlay: Button
    private lateinit var btnBluetooth: Button
    private lateinit var txtStatus: TextView
    private lateinit var txtAngles: TextView
    private lateinit var btnRecenter: Button
    private lateinit var sliderSensitivity: Slider
    private lateinit var sliderDwell: Slider
    private lateinit var lblSensitivity: TextView
    private lateinit var lblDwellDuration: TextView

    private val telemetryReceiver = object : BroadcastReceiver() {
        override fun onReceive(context: Context?, intent: Intent?) {
            if (intent == null) return
            if (intent.hasExtra(AirPodsMotionService.EXTRA_STATUS)) {
                val status = intent.getStringExtra(AirPodsMotionService.EXTRA_STATUS) ?: ""
                txtStatus.text = "Status: $status"
            }
            if (intent.hasExtra(AirPodsMotionService.EXTRA_YAW)) {
                val y = intent.getDoubleExtra(AirPodsMotionService.EXTRA_YAW, 0.0)
                val p = intent.getDoubleExtra(AirPodsMotionService.EXTRA_PITCH, 0.0)
                val r = intent.getDoubleExtra(AirPodsMotionService.EXTRA_ROLL, 0.0)
                txtAngles.text = String.format("Yaw: %+.1f° | Pitch: %+.1f° | Roll: %+.1f°", y, p, r)
            }
        }
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_main)

        initViews()
        setupListeners()
    }

    override fun onResume() {
        super.onResume()
        updatePermissionStatus()
        val filter = IntentFilter(AirPodsMotionService.ACTION_TELEMETRY)
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
            registerReceiver(telemetryReceiver, filter, RECEIVER_NOT_EXPORTED)
        } else {
            registerReceiver(telemetryReceiver, filter)
        }
    }

    override fun onPause() {
        super.onPause()
        try {
            unregisterReceiver(telemetryReceiver)
        } catch (_: Exception) {}
    }

    private fun initViews() {
        switchService = findViewById(R.id.switchService)
        btnAccessibility = findViewById(R.id.btnAccessibility)
        btnOverlay = findViewById(R.id.btnOverlay)
        btnBluetooth = findViewById(R.id.btnBluetooth)
        txtStatus = findViewById(R.id.txtStatus)
        txtAngles = findViewById(R.id.txtAngles)
        btnRecenter = findViewById(R.id.btnRecenter)
        sliderSensitivity = findViewById(R.id.sliderSensitivity)
        sliderDwell = findViewById(R.id.sliderDwell)
        lblSensitivity = findViewById(R.id.lblSensitivity)
        lblDwellDuration = findViewById(R.id.lblDwellDuration)

        val running = AirPodsMotionService.instance != null
        switchService.isChecked = running
    }

    private fun setupListeners() {
        // Toggle Master Service
        switchService.setOnCheckedChangeListener { _, isChecked ->
            if (isChecked) {
                if (!checkAllPermissions()) {
                    switchService.isChecked = false
                    Toast.makeText(this, "Please grant all required permissions first", Toast.LENGTH_SHORT).show()
                    return@setOnCheckedChangeListener
                }
                startService(Intent(this, AirPodsMotionService::class.java))
                startService(Intent(this, DwellOverlayService::class.java))
            } else {
                stopService(Intent(this, AirPodsMotionService::class.java))
                stopService(Intent(this, DwellOverlayService::class.java))
                txtStatus.text = "Status: Stopped"
            }
        }

        // Accessibility Intent
        btnAccessibility.setOnClickListener {
            startActivity(Intent(Settings.ACTION_ACCESSIBILITY_SETTINGS))
        }

        // System Alert Window Overlay Intent
        btnOverlay.setOnClickListener {
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M) {
                val intent = Intent(
                    Settings.ACTION_MANAGE_OVERLAY_PERMISSION,
                    Uri.parse("package:$packageName")
                )
                startActivity(intent)
            }
        }

        // Bluetooth Permissions
        btnBluetooth.setOnClickListener {
            requestBluetoothPermissions()
        }

        // Recenter Button
        btnRecenter.setOnClickListener {
            AirCursorAccessibilityService.instance?.recenter()
            Toast.makeText(this, "Head zero pose recentered", Toast.LENGTH_SHORT).show()
        }

        // Sensitivity Slider
        sliderSensitivity.addOnChangeListener { _, value, _ ->
            lblSensitivity.text = String.format("Pointer Sensitivity: %.1fx", value)
            AirPodsMotionService.instance?.settings?.pointer?.sensitivity = value.toDouble()
        }

        // Dwell Duration Slider
        sliderDwell.addOnChangeListener { _, value, _ ->
            lblDwellDuration.text = String.format("Dwell Click Time: %.1fs", value)
            AirPodsMotionService.instance?.settings?.dwell?.duration = value.toDouble()
        }
    }

    // --------------------------------------------------------------------------
    // Permissions Checklist & State
    // --------------------------------------------------------------------------

    private fun updatePermissionStatus() {
        // 1. Accessibility Service
        val a11yGranted = isAccessibilityServiceEnabled()
        btnAccessibility.text = if (a11yGranted) "Active" else "Grant"
        btnAccessibility.isEnabled = !a11yGranted

        // 2. Overlay Permission
        val overlayGranted = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M) {
            Settings.canDrawOverlays(this)
        } else true
        btnOverlay.text = if (overlayGranted) "Active" else "Grant"
        btnOverlay.isEnabled = !overlayGranted

        // 3. Bluetooth Permission
        val btGranted = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
            ContextCompat.checkSelfPermission(this, Manifest.permission.BLUETOOTH_CONNECT) == PackageManager.PERMISSION_GRANTED
        } else true
        btnBluetooth.text = if (btGranted) "Active" else "Grant"
        btnBluetooth.isEnabled = !btGranted
    }

    private fun isAccessibilityServiceEnabled(): Boolean {
        val am = getSystemService(Context.ACCESSIBILITY_SERVICE) as AccessibilityManager
        val enabledServices = am.getEnabledAccessibilityServiceList(AccessibilityServiceInfo.FEEDBACK_GENERIC)
        for (service in enabledServices) {
            if (service.resolveInfo.serviceInfo.packageName == packageName) {
                return true
            }
        }
        return false
    }

    private fun checkAllPermissions(): Boolean {
        val a11y = isAccessibilityServiceEnabled()
        val overlay = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M) Settings.canDrawOverlays(this) else true
        val bt = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
            ContextCompat.checkSelfPermission(this, Manifest.permission.BLUETOOTH_CONNECT) == PackageManager.PERMISSION_GRANTED
        } else true
        return a11y && overlay && bt
    }

    private fun requestBluetoothPermissions() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
            ActivityCompat.requestPermissions(
                this,
                arrayOf(Manifest.permission.BLUETOOTH_CONNECT, Manifest.permission.BLUETOOTH_SCAN),
                101
            )
        } else {
            Toast.makeText(this, "Bluetooth permission granted automatically", Toast.LENGTH_SHORT).show()
        }
    }

    override fun onRequestPermissionsResult(requestCode: Int, permissions: Array<out String>, grantResults: IntArray) {
        super.onRequestPermissionsResult(requestCode, permissions, grantResults)
        updatePermissionStatus()
    }
}
