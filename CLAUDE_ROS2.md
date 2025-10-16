# ROS2 Focus Control - Claude Context Documentation

## Last Updated: 2025-09-16

## Quick Recovery After Reboot

### Essential Commands
```bash
# 1. Source ROS2 workspace
cd /space/ros2_ws
source install/setup.bash

# 2. Start focus service (if needed)
cd /space/projects/project_icarus
./start_focus_service.sh

# 3. Run Flask app
python3 app.py
```

## PGM Camera Fix Details (2025-09-16)

### Problem Identified
- Framos FSM IMX cameras: Work correctly with `data_rate=0`
- Framos PGM IMX cameras: Failed with default `data_rate=1`
- Symptom: Buffering issues preventing live feed

### Solution Applied
Added V4L2 control to set `data_rate=0` before camera initialization.

### Modified Files
1. **focus_session.py** (lines 400-417)
   ```python
   # Set V4L2 data_rate to 0 for PGM camera compatibility
   video_device = f"/dev/video{self.camera_id}"
   subprocess.run(["v4l2-ctl", "--device", video_device, "--set-ctrl", "data_rate=0"])
   ```

2. **visual_test_overlay.py** (lines 95-112)
   - Same V4L2 control added before VideoCapture

### Verification
```bash
# Check current data_rate
v4l2-ctl --device=/dev/video0 --get-ctrl=data_rate

# Test camera with fix
python3 /space/projects/project_icarus/test_pgm_camera_fix.py 0
```

## Focus Control Package Structure

```
/space/ros2_ws/src/focus_control/
├── focus_control/
│   ├── focus_session.py      # Main focus algorithm & camera init
│   ├── focus_script.py       # ROS2 node & service handlers
│   ├── focus_runner.py       # Focus process runner
│   ├── focus_plotter.py      # Real-time plotting
│   ├── focus_positions_config.py  # Position management
│   └── tools/
│       ├── calibration_normalizer.py
│       └── focus_shape_matcher.py
├── package.xml
├── setup.py
└── setup.cfg
```

## Key Code Locations

### Camera Initialization
**File**: `/space/ros2_ws/src/focus_control/focus_control/focus_session.py`
- Function: `start_camera()` (around line 395)
- V4L2 fix: Lines 400-417
- Pipeline definitions: Lines 420-423

### ROS2 Service Handlers
**File**: `/space/ros2_ws/src/focus_control/focus_control/focus_script.py`
- Services: `start_focusing`, `stop_focusing`
- Topics: `set_camera`, `focus_score`, `motor_command`

### Visual Test Feed
**File**: `/space/projects/project_icarus/visual_test_overlay.py`
- V4L2 fix: Lines 95-112
- Called by Flask route in `app/blueprints/visual_test.py`

## Building and Running

### After Code Changes
```bash
cd /space/ros2_ws
colcon build --packages-select focus_control
source install/setup.bash
```

### Check ROS2 Status
```bash
ros2 node list
ros2 service list | grep focus
ros2 topic list | grep focus
```

### Monitor Focus Process
```bash
# Watch focus scores
ros2 topic echo /focus_score

# Watch motor commands
ros2 topic echo /motor_command

# Check focus completion
ros2 topic echo /focus_complete
```

## Important Constants

### File Paths (hardcoded in focus_session.py)
- Positions: `/home/ubuntu/space/projects/project_icarus/positions.json`
- Current position: `/home/ubuntu/space/projects/project_icarus/current_position.json`
- Lens config: `/space/ros2_ws/lens_config.json`
- Focus logs: `/home/ubuntu/focus_logs/`

### Camera Settings
- Default resolution: 1280x720
- Frame rate: 30 FPS
- Format: BGR (after conversion from NV12)
- Data rate: 0 (891/594 Mbps/lane) - MUST BE SET

## Debugging Camera Issues

### 1. Check V4L2 Controls
```bash
# List all controls
v4l2-ctl --device=/dev/video0 --list-ctrls-menus

# Check data_rate specifically
v4l2-ctl --device=/dev/video0 --get-ctrl=data_rate
```

### 2. Test GStreamer Pipeline
```bash
# Test pipeline directly
gst-launch-1.0 nvarguscamerasrc sensor-position=0 ! nvvidconv ! autovideosink
```

### 3. Check Camera Driver
```bash
# Check if camera is detected
ls /dev/video*

# Check dmesg for camera errors
dmesg | grep -i camera
```

## Flask Integration

### WebSocket Events (websocket_handlers.py)
- `start_visual_test`: Launches visual_test_overlay.py
- `stop_visual_test`: Kills the process
- `camera_frame`: Sends frames to frontend

### Blueprint Routes
- `/focus_management` - Main focus control page
- `/start_visual_test_feed` - Starts camera stream
- `/stop_visual_test_feed` - Stops camera stream

## Critical Notes

1. **Always set data_rate=0** before opening camera
2. **Rebuild after modifying** focus_control package
3. **Source workspace** after rebuild
4. **Check V4L2 controls** if camera fails
5. **Monitor ROS2 topics** for debugging

## Recovery Commands

If focus system is not responding:
```bash
# Kill all focus-related processes
pkill -f focus

# Clean restart
cd /space/projects/project_icarus
./clean_restart_focus.sh

# Rebuild if needed
cd /space/ros2_ws
colcon build --packages-select focus_control --cmake-clean-cache
source install/setup.bash
```