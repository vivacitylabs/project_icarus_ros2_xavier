# Focus Positions Configuration System

This system provides an easy way to adjust saved positions used during the focusing process.

## Key Positions

### 1. Hold Lens Position (ZA Axis)
- **ZA Position**: Position for both Z and A axes (default: 59.0mm)
- Both Z and A axes move together as a parallel gantry system
- Used when moving the gantry to hold the lens during focus

### 2. Camera Positions (B Axis)
- **Camera 0-5**: Different B-axis positions for each camera module
- Used to position the camera module holder for different camera angles

### 3. Servo Positions
- **Home**: Safe/parked position (default: 120°)
- **Active**: Position for holding lens (default: 34°)

### 4. Post-Focus Parameters
- **Lift Distance**: How far to lift ZA after focus (default: 5.0mm)
- **Dot Laser Duration**: How long to activate dot laser (default: 8.0s)

## How to Update Positions

### Method 1: Web UI (Recommended)
1. Go to Hardware Control page
2. Click on "Focus Positions Configuration" section
3. Adjust values and click Update buttons

### Method 2: Command Line
```bash
cd /space/ros2_ws

# Show current positions
python3 update_focus_positions.py

# Update hold lens position (ZA moves together)
python3 update_focus_positions.py hold_lens 60

# Update camera position
python3 update_focus_positions.py camera 0 -5.0

# Update servo positions
python3 update_focus_positions.py servo home 120
python3 update_focus_positions.py servo active 35

# Update post-focus parameters
python3 update_focus_positions.py post lift 6.0
python3 update_focus_positions.py post laser 10.0
```

### Method 3: Python Script
```python
from focus_positions_config import FocusPositionsConfig

config = FocusPositionsConfig()

# Update hold lens (ZA moves together)
config.update_hold_lens_position(z=60.0, a=60.0)  # Both values should be the same

# Update camera
config.update_camera_position(camera_num=0, b_position=-5.0)

# Show all positions
config.print_config()
```

## Configuration File Locations

### Main Positions (Hold Lens & Camera)
The ZA (Hold_Lens) and B-axis (Camera) positions are stored in the main positions file:
```
/space/projects/project_icarus/positions.json
```

### Focus Parameters (Servo & Post-Focus)
Servo positions and post-focus parameters are stored separately:
```
/space/ros2_ws/src/focus_control/focus_control/focus_params.json
```

## Important Notes
- Changes take effect immediately for the next focus session
- The focus system automatically uses the updated positions
- Hold Lens and Camera positions are shared with the hardware control system
- All systems (hardware control, distance control, focus control) now use the same position data
- Always test after making changes to ensure positions are correct