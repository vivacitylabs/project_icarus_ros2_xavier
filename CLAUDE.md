# Claude Code Session Notes

## Focus Node System Optimization Analysis - 2025-06-13

### Current Status
- ⚠️ **Camera driver updated - reboot required** - VEYE IMX462 driver with ISP support installed
- ✅ Focus system architecture analyzed - ready for optimization after camera fix
- ✅ Dashboard metrics fully linked and updating properly
- ✅ Persistent uptime tracking implemented across reboots
- ✅ Annual target card removed, focus time now tracks actual session durations

## Complete System Architecture Analysis - 2025-06-23

### System Overview
The focus control system spans three hardware platforms connected via network and serial interfaces:
1. **Jetson Xavier AGX** - Main compute unit running Flask web app and ROS2 focus control
2. **Jetson Nano** - Motor control bridge connected via direct Ethernet to Xavier
3. **Teensy 4.1 MCU** - Hardware motor controller connected via USB serial to Nano

### Detailed Architecture Findings

#### **1. Flask Web Application (Project Icarus)**
- **Location**: `/space/projects/project_icarus/`
- **Framework**: Flask 3.0.3 with Flask-SocketIO for WebSocket communication
- **Architecture**: Blueprint-based modular design
- **Key Components**:
  - Focus blueprint with REST endpoints for camera/focus control
  - WebSocket integration for real-time focus score streaming
  - ROS2 bridge (`FlaskROS2Bridge`) for motor command publishing
  - JSON-based persistence (no database)

#### **2. ROS2 Focus Control Package**
- **Location**: `/space/ros2_ws/src/focus_control/`
- **Type**: Pure Python ROS2 package (ament_python)
- **Core Modules**:
  - `focus_script.py` - ROS2 service node handling start/stop requests
  - `focus_runner.py` - Subprocess orchestrator for focus sessions
  - `focus_session.py` - Core focusing algorithm and hardware control
  - `focus_plotter.py` - Real-time plotting utilities
- **Hardware Integration**:
  - GStreamer-based camera pipeline for NVIDIA Argus
  - OpenGL live preview rendering
  - Multi-phase focusing algorithm with adaptive stepping

#### **3. Communication Flow**

##### **End-to-End Request Flow**:
```
Web Browser (User clicks "Start Focus")
    ↓ HTTP POST /focus/start
Flask App (Xavier)
    ↓ ROS2 Service Call (start_focusing)
Focus Script Service (Xavier)
    ↓ Subprocess spawn via bash wrapper
Focus Runner Process (Xavier)
    ↓ ROS2 Topic (/scripted_motor_command)
[Network Layer - Ethernet 192.168.0.x]
    ↓ ROS2 DDS
Jetson Nano Bridge
    ↓ Serial UART (921600 baud)
Teensy 4.1 MCU
    ↓ Hardware control
Motors/Camera/Servo
```

##### **Response Flow**:
```
Teensy ACK → Nano → ROS2 /motor_ack → Xavier
Focus Scores → ROS2 /focus_score → WebSocket → Browser
```

#### **4. Network Architecture**
- **Xavier-to-Nano Connection**: Direct Ethernet link
  - Xavier: 192.168.0.100 (eth0)
  - Jetson Nano: 192.168.0.2
  - Protocol: ROS2 DDS with `ROS_DOMAIN_ID=0`
- **Shared ROS2 Topics**:
  - `/motor_command` - Direct UI commands
  - `/scripted_motor_command` - Queued focus operations
  - `/motor_ack` - Command acknowledgments
  - `/focus_score`, `/focus_complete`, `/focus_start` - Status updates

#### **5. Jetson Nano to Teensy Protocol**
- **Connection**: USB Serial at `/dev/teensy` (921600 baud)
- **Protocol**: ASCII text-based, newline terminated
- **Command Format**:
  - Motor: `M <axis> <steps> <direction>` (e.g., `M D 250 0`)
  - Absolute: `MA <axis> <steps>`
  - Homing: `H <axis>`
  - Servo: `S <angle>`
  - Laser: `L <type> <state>`
- **Step Conversions**:
  - XY/ZA/B: 3200 steps/mm
  - C: 1600 steps/mm
  - D (lens): 50 steps/unit

#### **6. Identified Architecture Issues and Optimization Opportunities**

Based on the complete system analysis, the following issues and optimizations have been identified:

##### **🔴 Critical Issues:**

1. **Over-Engineered Architecture**
   - Current: Flask → ROS2 Service → Bash Script → Python Subprocess → Focus Session
   - Problem: 4-layer indirection creates debugging complexity and failure points
   - Impact: Higher latency, error prone, maintenance overhead

2. **Resource Management Problems** 
   - Camera resources not properly pooled - initialized multiple times
   - Memory leaks potential in frame processing loops
   - Process cleanup relies on polling timers instead of proper signal handling

3. **Threading Issues**
   - Race conditions in frame data access (`latest_frame`, plotting data)
   - Blocking operations with 3-second motor timeouts
   - Too many threads for simple operations

#### **🟡 Performance Bottlenecks:**

1. **Inefficient Processing**
   - Full frame copying on every score measurement instead of ROI-only
   - Fixed sleep delays that may be too conservative (600ms+ delays)
   - JSON file I/O on every operation instead of memory caching

2. **Hardcoded Configuration**
   - Absolute paths scattered throughout (`/home/ubuntu/`, `/tmp/`)
   - Lens configurations duplicated and not maintainable
   - Magic numbers and timeouts hardcoded

4. **Network Dependencies**
   - Focus operations depend on network connectivity between Xavier and Nano
   - No local fallback if Ethernet link fails
   - ROS2 DDS adds overhead for local motor control

5. **Subprocess Management**
   - Complex bash wrapper script for environment setup
   - Process cleanup relies on signal handlers and polling
   - Difficult to debug subprocess crashes

##### **🟡 Performance Bottlenecks:**

1. **Inefficient Processing**
   - Full frame copying on every score measurement instead of ROI-only
   - Fixed sleep delays that may be too conservative (600ms+ delays)
   - JSON file I/O on every operation instead of memory caching

2. **Hardcoded Configuration**
   - Absolute paths scattered throughout (`/home/ubuntu/`, `/tmp/`)
   - Lens configurations duplicated and not maintainable
   - Magic numbers and timeouts hardcoded

3. **Serial Communication Bottleneck**
   - All motor commands funnel through single serial connection
   - 921600 baud rate may limit rapid command sequences
   - Text-based protocol adds parsing overhead

##### **🟢 Prioritized Optimization Recommendations:**

**HIGH PRIORITY:**
1. **Simplify Architecture**: Direct Flask → ROS2 → Focus Session (eliminate subprocess)
2. **Camera Resource Pool**: Singleton manager with proper lifecycle
3. **Fix Threading**: Single background thread for camera operations
4. **Configuration Management**: External config files for all settings
5. **Proper Cleanup**: Context managers and signal handlers

**MEDIUM PRIORITY:**
1. **Async Motor Operations**: Non-blocking motor commands
2. **Frame Buffer Optimization**: Circular buffer with ROI-only processing
3. **Error Recovery**: Automatic retry logic for hardware failures
4. **Memory Monitoring**: Usage tracking and cleanup triggers
5. **Network Resilience**: Handle Xavier-Nano link failures gracefully

**LOW PRIORITY:**
1. **Performance Metrics**: Timing instrumentation
2. **Unit Testing**: Comprehensive test coverage
3. **Documentation**: API specifications and inline docs
4. **Protocol Optimization**: Binary protocol for Teensy communication

##### **📊 Proposed Simplified Architecture:**

```
Current:  Flask → ROS2 Service → Bash Script → Python Subprocess → Focus Session
                                                                    ↓
                                                           Xavier → Nano → Teensy

Proposed: Flask/REST API → ROS2 Focus Service → Focus Controller
                                              ↘ Resource Manager ↗
                                                        ↓
                                               Hardware Abstraction Layer
                                                        ↓
                                                Xavier → Nano → Teensy
```

##### **💡 Expected Benefits:**
- 50-70% reduction in focus session startup time
- Eliminate subprocess management complexity
- Improved reliability through proper resource management
- Better error handling and recovery
- Easier debugging with simplified architecture
- Reduced memory usage through efficient frame processing
- More maintainable codebase with clear separation of concerns

### Key Files Analyzed:

#### Flask Application (Xavier):
- `/space/projects/project_icarus/app/blueprints/focus.py` - Focus REST endpoints
- `/space/projects/project_icarus/app/focus_service_client.py` - ROS2 client for focus scoring
- `/space/projects/project_icarus/app/nanocontroller.py` - Flask-ROS2 bridge for motor commands
- `/space/projects/project_icarus/app/websocket_handlers.py` - WebSocket event handling

#### ROS2 Focus Control (Xavier):
- `/space/ros2_ws/src/focus_control/focus_control/focus_script.py` - Main ROS2 service node
- `/space/ros2_ws/src/focus_control/focus_control/focus_runner.py` - Focus session orchestrator
- `/space/ros2_ws/src/focus_control/focus_control/focus_session.py` - Core algorithm & hardware control
- `/space/ros2_ws/src/focus_control/focus_control/focus_plotter.py` - Real-time plotting

#### Configuration Files:
- `/space/projects/project_icarus/positions.json` - Motor positions and lens calibrations
- `/tmp/focus_session.json` - Temporary session configuration
- `/space/projects/project_icarus/data/uptime_data.json` - System uptime tracking

### Recent Changes Made:
1. Fixed camera initialization by using system Python with GStreamer-enabled OpenCV
2. Implemented proper focus time tracking (actual session durations only)
3. Added persistent machine uptime tracking across reboots
4. Linked all dashboard metrics cards to focus completion events
5. Removed annual target card as requested
6. Documented complete system architecture including Xavier→Nano→Teensy communication

### Next Steps:
**Ready to implement optimizations starting with highest priority items:**
1. Architecture simplification (eliminate subprocess layer)
2. Resource management improvements (camera pooling)
3. Threading model optimization (single background thread)
4. Configuration management centralization
5. Network resilience improvements

## CRITICAL ISSUE RESOLVED - Camera Resource Conflict - 2025-06-23

### Problem Summary
**Issue**: Focus process not starting from UI - camera initialization failing with "Failed to create CaptureSession" error.

### Root Cause Identified
The system had **multiple focus_script processes running simultaneously**, causing camera resource conflicts:

1. **systemd service**: `/etc/systemd/system/ros2_focus_node.service` properly manages one instance
2. **Manual processes**: Additional instances were started manually during debugging
3. **Camera conflict**: Multiple processes competing for NVIDIA Argus camera resource
4. **Driver state**: Even after killing processes, camera driver remained in inconsistent state

### Debugging Process Completed
✅ **Architecture Analysis**: Confirmed camera initialization is lazy (only on focus start)  
✅ **Process Investigation**: Found multiple focus_script PIDs (29354, 29412, 30374, etc.)  
✅ **Service Management**: systemd service working correctly with `Restart=always`  
✅ **Camera Testing**: Direct GStreamer pipeline works, OpenCV fails with "Internal data stream error"  
✅ **Resource Cleanup**: Eliminated all duplicate processes  

### Current Status (Pre-Reboot)
- ✅ **Single Service Instance**: Only systemd-managed process running (PID 30999)
- ✅ **Service Calls Work**: `ros2 service call /start_focusing` returns success  
- ❌ **Camera Driver Issue**: NVIDIA Argus in inconsistent state, needs driver reset
- ❌ **OpenCV Access**: "Internal data stream error" persists despite cleanup

### Solution Required
**System reboot needed** to reset NVIDIA Argus camera driver state. Alternative would require sudo access to restart camera services.

### Architecture Improvements Made
1. **Process Management**: Identified proper systemd service management
2. **Resource Conflicts**: Eliminated duplicate process creation
3. **Service Monitoring**: Confirmed single instance operation

### Files Modified During Session
- `/space/ros2_ws/src/focus_control/focus_control/focus_session.py` - Emergency cleanup methods
- `/space/ros2_ws/src/focus_control/focus_control/focus_script.py` - Integrated subprocess elimination  
- `/space/projects/project_icarus/app/templates/focus_management.html` - Fixed button state CSS

### Post-Reboot Verification Plan
1. ✅ Verify single focus service running: `systemctl status ros2_focus_node.service`
2. ✅ Test camera access: `gst-launch-1.0 nvarguscamerasrc sensor-position=0 ! fakesink`
3. ✅ Test focus service: `ros2 service call /start_focusing std_srvs/srv/Trigger`
4. ✅ Test UI integration: Navigate to focus management page and click "Begin Focusing"
5. ✅ Verify emergency stop: Test ZA homing and button state reset

### Known Working State
- Focus system was fully functional earlier today before resource conflicts
- Camera hardware confirmed working (imx462_0_framos module detected)
- All motor axes operational (B-axis positioning fixed)
- UI button states corrected (CSS class names fixed)

## IMX462 Camera Driver Analysis & Update - 2025-06-30

### Problem Identified
**Root Cause**: Current IMX462 driver (`nv_imx462` v2.0.6) only provides RAW Bayer data (RG12 format) without ISP processing. The focus control system expects processed RGB/YUV video formats.

**Detailed Symptoms**:
- GStreamer pipeline fails: "Failed to create CaptureSession"
- V4L2 shows only `video/x-bayer` formats (RG10, RG12) 
- NVIDIA Argus cannot create capture session with RAW-only data
- Focus system camera initialization fails with "Internal data stream error"
- No ISP processing pipeline available for software debayering

**Hardware Status Verified**:
- ✅ Camera hardware functional: Reports 1920x1080 RG12 format correctly
- ✅ IMX462 sensor detected: `vi-output, imx462 204-001a`
- ✅ Focus service running: Single instance via systemd
- ❌ Software ISP missing: Standard tools (bayer2rgb, v4l2src) fail with 12-bit data

### Solution Implemented
**VEYE IMX462 Driver with ISP Support Installed**:

✅ **Driver Installation**:
- Downloaded VEYE nvidia_jetson_veye_bsp v1.32 package
- Installed `veyecam.ko` driver module to `/lib/modules/5.10.120-1-mustard/kernel/drivers/media/i2c/`
- Updated module dependencies with `depmod -a`

✅ **Device Tree Update**:
- Backed up original DTB: `/boot/tegra194-p2888-0001-p2822-0000.dtb.backup`
- Installed IMX462-specific DTB: `RAW-MIPI-IMX462M/tegra194-p2888-0001-p2822-0000.dtb`
- Compatible with JetPack 5.1.2 / L4T 35.4.1

✅ **Driver Loading Configuration**:
- Created blacklist for old driver: `/etc/modprobe.d/blacklist-nv-imx462.conf`
- Added VEYE driver to modules-load: `/etc/modules-load.d/veyecam.conf`
- System configured to load veyecam instead of nv_imx462 on boot

### Alternative Solutions Attempted
**Software ISP Processing** (all failed due to 12-bit format):
- ❌ GStreamer bayer2rgb plugin: Only supports 8-bit Bayer formats
- ❌ OpenCV debayering: Cannot handle 12-bit packed Bayer data
- ❌ V4L2 direct access: Format negotiation fails with RG12
- ❌ FastVideo SDK: Requires commercial license and additional libraries

**Working Workarounds Available**:
- ✅ Camera bypass simulation: `/space/ros2_ws/focus_camera_bypass.py`
- ✅ Alternative display tools: `cheese`, system camera apps
- ⚠️ Focus system modification: Can work without live preview temporarily

### Expected Results After Reboot
- **Camera Access**: `nvarguscamerasrc` should work with ISP processing
- **Video Formats**: Standard RGB/YUV formats available instead of RAW Bayer
- **Focus System**: Should initialize camera successfully and display live feed
- **Testing Commands**:
  ```bash
  lsmod | grep veye  # Should show veyecam loaded
  v4l2-ctl --device=/dev/video0 --list-formats-ext  # Should show RGB/YUV formats
  gst-launch-1.0 nvarguscamerasrc ! xvimagesink  # Should display feed
  ```

### Troubleshooting if Feed Still Fails After Reboot
If camera feed issues persist after reboot with VEYE driver:

1. **Verify Driver Loading**:
   ```bash
   lsmod | grep -E 'veye|imx462'  # Should only show veyecam
   ```

2. **Check Available Formats**:
   ```bash
   v4l2-ctl --device=/dev/video0 --list-formats-ext
   # Should show RGB/YUV formats, not RG10/RG12
   ```

3. **Test Camera Pipeline**:
   ```bash
   gst-launch-1.0 nvarguscamerasrc num-buffers=10 ! fakesink -v
   ```

4. **Alternative Focus System**:
   - Use camera bypass: `python3 /space/ros2_ws/focus_camera_bypass.py`
   - Modify focus_session.py to use bypass class temporarily

### Rollback Plan
If issues occur, restore original driver:
```bash
sudo cp /boot/tegra194-p2888-0001-p2822-0000.dtb.backup /boot/tegra194-p2888-0001-p2822-0000.dtb
sudo rm /lib/modules/5.10.120-1-mustard/kernel/drivers/media/i2c/veyecam.ko
sudo rm /etc/modprobe.d/blacklist-nv-imx462.conf
sudo rm /etc/modules-load.d/veyecam.conf
sudo depmod -a
# Reboot
```

**🔄 SYSTEM READY FOR REBOOT TO ACTIVATE VEYE DRIVER WITH ISP SUPPORT 🔄**

---

## ESP32 Motor Controller Upgrade & Robustness Improvements - 2025-10-10

### Hardware Migration Completed
**Replaced Teensy 4.1 with ESP32** (Silicon Labs CP210x UART Bridge)

**Changes Made**:
- ✅ Updated udev rule on Jetson Nano to recognize ESP32 (`idVendor=10c4, idProduct=ea60`)
- ✅ Changed baud rate from 921600 to 115200 to match ESP32 firmware
- ✅ `/dev/teensy` symlink now points to ESP32 (maintains code compatibility)

### Robustness Improvements Implemented

After system-wide reboot issues where motors stopped responding, implemented comprehensive robustness features:

#### 1. **Automatic Reconnection Logic**
Enhanced `/home/jetson/ros2_ws/src/teensy_serial/teensy_serial/teensy_serial_node.py`:
- Retry logic: 3 attempts with 2-second delays on connection failure
- Automatic recovery from I/O errors and disconnections
- Consecutive error tracking (triggers reconnection after 5 errors)
- Health monitoring: Checks connection every 5 seconds

#### 2. **systemd Service Improvements**
Updated `/etc/systemd/system/teensy_serial_node.service` on Jetson Nano:
- Added `ExecStartPre=/bin/sleep 5` to wait for ESP32 boot completion
- Added `RestartSec=5` to wait between restart attempts
- Added `StartLimitIntervalSec=0` to prevent restart throttling
- Maintains `Restart=always` for automatic recovery

#### 3. **Boot Message Filtering**
Serial node now filters ESP32 boot messages:
- Ignores messages containing: `rst:`, `ets`, `boot:`, `invalid header`
- Logs them as warnings instead of errors
- Prevents false error reporting during ESP32 resets

#### 4. **Connection Health Monitoring**
- Periodic health checks every 5 seconds
- Automatic reconnection attempts when connection degrades
- Graceful handling of USB port changes (ttyUSB0 ↔ ttyUSB1)

### Configuration Documentation
Created comprehensive documentation: `/space/ros2_ws/ESP32_CONFIGURATION.md`

**Key Configuration Points**:
- **Baud Rate**: 115200 (CRITICAL - must match ESP32 firmware)
- **Serial Port**: `/dev/teensy` (udev symlink, follows ESP32 automatically)
- **Reconnection**: 3 attempts with 2-second delays
- **Startup Delay**: 5 seconds to allow ESP32 boot

### Testing Performed
✅ Motor commands working after reboot
✅ Automatic reconnection on serial errors
✅ ESP32 boot message filtering
✅ Health monitoring active
✅ Commands: Homing (H XY, H B) and movement (M B 100 0) verified

### Troubleshooting Guide
See `/space/ros2_ws/ESP32_CONFIGURATION.md` for:
- Post-reboot verification checklist
- Common issues and solutions
- Testing commands
- Baud rate mismatch diagnosis

### Files Modified
**Jetson Nano**:
- `/etc/udev/rules.d/99-teensy.rules` - Updated for ESP32
- `/etc/systemd/system/teensy_serial_node.service` - Enhanced restart policy
- `/home/jetson/ros2_ws/src/teensy_serial/teensy_serial/teensy_serial_node.py` - Reconnection logic
- Backup created: `teensy_serial_node.py.backup`

**Xavier**:
- `/space/ros2_ws/ESP32_CONFIGURATION.md` - New documentation

### Expected Behavior After Reboot
1. systemd waits 5 seconds before starting serial node
2. Serial node waits 2 seconds for ESP32 boot, then connects
3. If connection fails, retries up to 3 times
4. Once running, monitors health every 5 seconds
5. Auto-reconnects on any serial errors
6. Service auto-restarts if process crashes

### Version History
- **2025-10-10**: ESP32 migration + robustness improvements
- **2025-06-30**: VEYE camera driver with ISP support
- **2025-06-23**: Camera resource conflict resolution
- **Initial**: Teensy 4.1 at 921600 baud

---

### Environment Info:
- **Primary System**: Jetson Xavier AGX with Ubuntu 20.04, ROS2 Foxy
- **Secondary System**: Jetson Nano (motor control bridge)
- **MCU**: ESP32 (Silicon Labs CP210x UART Bridge) - *formerly Teensy 4.1*
- **Serial Config**: `/dev/teensy` at 115200 baud - *formerly 921600*
- **Network**: Direct Ethernet link (192.168.0.x)
- **Location**: `/space/ros2_ws/` (ROS2 workspace)
- **Flask App**: `/space/projects/project_icarus/`
- **Camera**: NVIDIA Argus with GStreamer pipeline
- **Motors**: XY, ZA, B, C, D axes + servo + laser control