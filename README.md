# Project Icarus - ROS2 Xavier Workspace

**ROS2 workspace for autonomous camera focus control on NVIDIA Jetson Xavier**

This workspace contains the ROS2 packages and nodes for the Project Icarus automated focus system. It provides real-time camera control, focus algorithm implementation, and hardware integration for multi-camera vision systems.

## Overview

The focus control system uses ROS2 services and topics to manage camera initialization, focus scoring, motor control, and position management. It integrates with NVIDIA Argus cameras via GStreamer and provides a robust framework for automated focusing.

The system communicates with a Jetson Nano slave controller via direct Ethernet connection. The Nano parses and relays movement commands to an ESP32 microcontroller over USB serial for precise stepper motor control.

## Architecture

```
┌─────────────────────────────────────────────────┐
│         Jetson Xavier (ROS2 Master)             │
│  ┌─────────────────────────────────────────┐   │
│  │  Focus Control Node                     │   │
│  │  - Camera capture & focus algorithm     │   │
│  │  - Focus score calculation              │   │
│  │  - Decision logic                       │   │
│  └──────────────────┬──────────────────────┘   │
└────────────────────┼───────────────────────────┘
                     │ Direct Ethernet
                     ↓
┌─────────────────────────────────────────────────┐
│         Jetson Nano (Slave Controller)          │
│  ┌─────────────────────────────────────────┐   │
│  │  Serial Relay Controller                │   │
│  │  - Command parsing                       │   │
│  │  - Protocol conversion                   │   │
│  │  - Position tracking                     │   │
│  └──────────────────┬──────────────────────┘   │
└────────────────────┼───────────────────────────┘
                     │ USB Serial
                     ↓
        ┌────────────────────────┐
        │  ESP32 Motor Controller │
        │  - Stepper motor driver │
        │  - Position tracking    │
        │  - Movement execution   │
        └────────────────────────┘
```

## Contents

### Packages

- **focus_control**: Main package for camera focus automation
  - `focus_script.py` - ROS2 node providing focus control services
  - `focus_session.py` - Camera initialization and focus algorithm
  - `focus_runner.py` - Focus process orchestration
  - `focus_plotter.py` - Real-time focus score visualization
  - `focus_positions_config.py` - Position configuration management

### Configuration Files

- `lens_config.json` - Lens parameters and calibration data
- `focus_params.json` - Focus algorithm parameters
- `focus_positions.json` - Saved focus positions

### Utility Scripts

- `start_focus_node.sh` - Quick start script for focus service
- `update_lens_config.py` - Tool for updating lens calibration
- `update_focus_positions.py` - Tool for managing focus positions
- `focus_camera_bypass.py` - Direct camera access testing

## Requirements

### Hardware
- **NVIDIA Jetson Xavier** - Primary controller (ROS2 master)
- **NVIDIA Jetson Nano** - Slave controller for motor communication
- **Direct Ethernet Connection** - Xavier to Nano communication
- **ESP32 Microcontroller** - Motor driver interface
- **USB Serial Cable** - Nano to ESP32 connection
- **Framos PGM/FSM IMX Cameras** - CSI interface
- **Stepper Motor Controller** - Focus mechanism
- **I2C EEPROM Modules** - Optional, for lens storage

### Software
- Ubuntu 18.04+ (Jetson Linux)
- ROS2 Eloquent or later
- Python 3.6+
- OpenCV 4.x with CUDA support
- GStreamer with NVIDIA Argus plugins
- NumPy, SciPy, Matplotlib

## Installation

### 1. Clone the Repository

```bash
# Clone to /space/ros2_ws
git clone https://github.com/vivacitylabs/project_icarus_ros2_xavier.git /space/ros2_ws
cd /space/ros2_ws
```

### 2. Install Dependencies

```bash
# Install ROS2 dependencies
sudo apt update
sudo apt install -y ros-eloquent-rclpy ros-eloquent-std-msgs ros-eloquent-std-srvs

# Install Python dependencies
pip3 install numpy scipy matplotlib opencv-python pyserial
```

### 3. Build the Workspace

```bash
# Build focus_control package
colcon build --packages-select focus_control

# Source the workspace
source install/setup.bash
```

### 4. Configure Network Connection

Set up the direct Ethernet connection between Xavier and Nano:

**On Xavier:**
```bash
# Configure static IP (example)
sudo ifconfig eth0 192.168.10.1 netmask 255.255.255.0
```

**On Nano:**
```bash
# Configure static IP (example)
sudo ifconfig eth0 192.168.10.2 netmask 255.255.255.0
```

Test connectivity:
```bash
ping 192.168.10.2  # From Xavier to Nano
```

### 5. Configure Camera System

For PGM cameras, ensure V4L2 data rate is configured:

```bash
# Set data_rate to 0 for PGM camera compatibility
v4l2-ctl --device=/dev/video0 --set-ctrl=data_rate=0
```

**Note**: The focus system automatically configures this during initialization.

### 6. Configure ESP32 Serial Connection

On the Jetson Nano, identify the USB serial device:

```bash
# List USB serial devices
ls -l /dev/ttyUSB* /dev/ttyACM*

# Typical device: /dev/ttyUSB0 or /dev/ttyACM0
```

See `ESP32_CONFIGURATION.md` for detailed ESP32 setup.

## Usage

### Starting the Focus Service

#### Using the Shell Script

```bash
cd /space/ros2_ws
./start_focus_node.sh
```

#### Manual Start

```bash
# Source ROS2 workspace
source /space/ros2_ws/install/setup.bash

# Run the focus control node
ros2 run focus_control focus_script
```

### ROS2 Services

The focus control node provides the following services:

#### Start Focusing
```bash
ros2 service call /start_focusing std_srvs/srv/Trigger
```

#### Stop Focusing
```bash
ros2 service call /stop_focusing std_srvs/srv/Trigger
```

#### Get Current Status
```bash
ros2 service call /get_focus_status std_srvs/srv/Trigger
```

### ROS2 Topics

#### Subscribe to Focus Score
```bash
ros2 topic echo /focus_score
```

#### Subscribe to Motor Commands
```bash
ros2 topic echo /motor_command
```

#### Set Camera
```bash
ros2 topic pub -1 /set_camera std_msgs/String "data: '0'"
```

#### Monitor Current Position
```bash
ros2 topic echo /current_position
```

### Monitoring and Debugging

```bash
# List all ROS2 nodes
ros2 node list

# List all services
ros2 service list

# List all topics
ros2 topic list

# Check node info
ros2 node info /focus_control_node
```

## Package Structure

```
ros2_ws/
├── src/
│   └── focus_control/
│       ├── focus_control/          # Python module
│       │   ├── focus_script.py     # Main ROS2 node
│       │   ├── focus_session.py    # Camera and focus logic
│       │   ├── focus_runner.py     # Process runner
│       │   ├── focus_plotter.py    # Visualization
│       │   ├── focus_positions_config.py
│       │   ├── focus_params.json
│       │   └── focus_positions.json
│       ├── resource/                # Package markers
│       ├── test/                    # Unit tests
│       ├── package.xml              # ROS2 package manifest
│       ├── setup.py                 # Python package setup
│       └── setup.cfg
├── lens_config.json                 # Lens calibration
├── start_focus_node.sh              # Quick start script
├── update_lens_config.py
├── update_focus_positions.py
└── README.md                        # This file
```

## Focus Algorithm

The focus system uses a variance-based sharpness metric calculated from the camera feed:

1. **Image Capture**: Grab frame from GStreamer pipeline
2. **ROI Extraction**: Extract Region of Interest (configurable radius)
3. **Sharpness Calculation**: Compute Laplacian variance
4. **Motor Control**: Send movement commands via Ethernet/USB serial chain
5. **Peak Detection**: Identify optimal focus position

### Motor Command Flow

1. **Xavier**: Focus algorithm determines required motor movement
2. **Xavier → Nano (Ethernet)**: Command sent over direct Ethernet connection to Jetson Nano
3. **Nano**: Parses and validates motor command, converts to serial protocol
4. **Nano → ESP32 (USB Serial)**: Relays formatted command via USB serial connection
5. **ESP32**: Executes stepper motor movement
6. **ESP32 → Nano → Xavier**: Position feedback and status updates returned through chain

### Key Parameters

Configured in `focus_params.json`:

- `roi_radius`: Region of interest as fraction of image size (default: 0.4)
- `step_size`: Motor steps per iteration
- `max_iterations`: Maximum search iterations
- `threshold`: Minimum acceptable focus score

## Camera Configuration

### Supported Cameras

- **Framos FSM-IMX** series
- **Framos PGM-IMX** series

### V4L2 Settings

The system automatically configures:
- `data_rate=0` (891/594 Mbps/lane for PGM compatibility)
- Exposure and gain settings
- Resolution and format

### GStreamer Pipeline

```
nvarguscamerasrc sensor-position={id} !
nvvidconv ! video/x-raw, format=BGRx !
videoconvert ! video/x-raw, format=BGR !
appsink drop=true
```

## Motor Control System

### Hardware Communication Chain

- **Jetson Xavier ↔ Jetson Nano**: Direct Ethernet (static IP networking)
- **Jetson Nano ↔ ESP32**: USB Serial (typically `/dev/ttyUSB0` or `/dev/ttyACM0`)

### Network Configuration

The Xavier and Nano communicate over a dedicated Ethernet link:
- **Xavier IP**: `192.168.10.1` (configurable)
- **Nano IP**: `192.168.10.2` (configurable)
- **Protocol**: TCP/IP socket communication
- **Port**: 5000 (default, configurable)

### Serial Configuration

The Nano communicates with ESP32 via USB serial:
- **Baud Rate**: 115200
- **Data Bits**: 8
- **Stop Bits**: 1
- **Parity**: None
- **Flow Control**: None

### Command Protocol

Motor commands are relayed through the communication chain:

**Xavier → Nano (Ethernet):**
```json
{
  "command": "MOVE",
  "direction": "forward",
  "steps": 100
}
```

**Nano → ESP32 (Serial):**
```
STEP F 100\n
```

**Available Commands:**
- `STEP <direction> <count>` - Move motor
- `GET_POS` - Query current position
- `HOME` - Return to home position
- `STOP` - Emergency stop
- `SET_SPEED <rpm>` - Set motor speed

## Position Management

### Saving Positions

Positions are automatically saved when focus completes. Manual management:

```python
python3 update_focus_positions.py --save <position_name> --value <steps>
```

### Loading Positions

```python
python3 update_focus_positions.py --load <position_name>
```

### Position Files

- `focus_positions.json` - In package directory (for specific lens)
- `/home/ubuntu/space/projects/project_icarus/positions.json` - Global positions

## Lens Configuration

Edit `lens_config.json` to configure lens parameters:

```json
{
  "lens_type": "50mm_f1.8",
  "min_focus_distance": 450,
  "max_focus_distance": 10000,
  "steps_per_mm": 100,
  "calibration_data": {}
}
```

Update using:

```bash
python3 update_lens_config.py
```

## Troubleshooting

### Node Won't Start

1. Check ROS2 installation:
   ```bash
   ros2 --version
   ```

2. Verify workspace is built:
   ```bash
   ls install/focus_control/
   ```

3. Source the workspace:
   ```bash
   source /space/ros2_ws/install/setup.bash
   ```

### Camera Not Detected

1. List video devices:
   ```bash
   ls -l /dev/video*
   ```

2. Check V4L2 controls:
   ```bash
   v4l2-ctl --device=/dev/video0 --list-ctrls
   ```

3. Test with direct capture:
   ```bash
   python3 focus_camera_bypass.py 0
   ```

### Network Connection Issues

1. Test Xavier to Nano connectivity:
   ```bash
   ping 192.168.10.2  # From Xavier
   ```

2. Check Ethernet interface status:
   ```bash
   ifconfig eth0
   ```

3. Verify firewall rules allow communication on port 5000

4. Test with telnet:
   ```bash
   telnet 192.168.10.2 5000
   ```

### Serial Connection Issues

1. On Nano, check USB serial device:
   ```bash
   ls -l /dev/ttyUSB* /dev/ttyACM*
   ```

2. Check permissions:
   ```bash
   sudo chmod 666 /dev/ttyUSB0
   # Or add user to dialout group:
   sudo usermod -aG dialout $USER
   ```

3. Test serial connection:
   ```bash
   screen /dev/ttyUSB0 115200
   ```

4. Monitor serial traffic:
   ```bash
   sudo cat /dev/ttyUSB0
   ```

### Motor Not Responding

1. Check Xavier to Nano Ethernet connection
2. Verify Nano to ESP32 USB serial connection
3. Check ESP32 power supply
4. Test motor controller directly via serial terminal
5. Check stepper motor wiring and power
6. Monitor motor command topic:
   ```bash
   ros2 topic echo /motor_command
   ```

### Focus Not Working

1. Check motor connection chain (Ethernet + Serial)
2. Verify focus parameters in `focus_params.json`
3. Monitor focus scores:
   ```bash
   ros2 topic echo /focus_score
   ```
4. Check logs:
   ```bash
   tail -f /home/ubuntu/focus_logs/focus_*.log
   ```

### Build Errors

1. Clean workspace:
   ```bash
   rm -rf build/ install/ log/
   ```

2. Rebuild:
   ```bash
   colcon build --packages-select focus_control
   ```

3. Check Python dependencies:
   ```bash
   pip3 list | grep -E "numpy|scipy|opencv|serial"
   ```

## Development

### Adding New Features

1. Modify Python files in `src/focus_control/focus_control/`
2. Rebuild the package:
   ```bash
   colcon build --packages-select focus_control
   ```
3. Source and test:
   ```bash
   source install/setup.bash
   ros2 run focus_control focus_script
   ```

### Code Style

- Follow PEP 8 for Python code
- Use meaningful variable names
- Document complex algorithms
- Add type hints where possible

### Testing

```bash
# Run package tests
colcon test --packages-select focus_control

# Run specific Python script
python3 src/focus_control/focus_control/focus_script.py
```

## Integration with Web Interface

This workspace integrates with the main Project Icarus web application:

**Web App Repository**: [vivacitylabs/project_icarus](https://github.com/vivacitylabs/project_icarus)

The web interface communicates with this ROS2 node via:
- ROS2 service calls for control
- ROS2 topic subscriptions for monitoring
- WebSocket forwarding for real-time updates
- Direct Ethernet communication with Jetson Nano controller for hardware management

## Documentation

Additional documentation files:

- `CLAUDE.md` - Developer context and implementation notes
- `CLAUDE_ROS2.md` - ROS2-specific development notes
- `ESP32_CONFIGURATION.md` - ESP32 motor controller setup and communication protocol
- `FOCUS_POSITIONS_README.md` - Detailed position management guide

## Contributing

This is a Vivacity Labs internal project.

1. Create feature branches from `main`
2. Test thoroughly on Jetson hardware
3. Update documentation for changes
4. Submit PRs with detailed descriptions

## License

Proprietary - Vivacity Labs Ltd.

## Support

For issues and support:
- Internal: Contact the Vision Systems team
- GitHub Issues: https://github.com/vivacitylabs/project_icarus_ros2_xavier/issues

## Related Repositories

- **Web Interface**: [vivacitylabs/project_icarus](https://github.com/vivacitylabs/project_icarus)
  - Flask-based web UI for controlling this ROS2 system
  - Hardware management and EEPROM utilities
  - Real-time monitoring and visualization
  - Jetson Nano controller interface

## Changelog

### Recent Updates

- **ESP32 Migration**: Transitioned from Teensy to ESP32 for motor control
- **Direct Ethernet**: Implemented Xavier-Nano dedicated Ethernet link
- **USB Serial Protocol**: Established robust Nano-ESP32 serial communication
- **V4L2 Auto-Configuration**: Automatic `data_rate=0` setting for PGM cameras
- **Position Management**: Enhanced focus position save/load system
- **Camera Selection Fix**: Improved camera switching reliability
- **Focus Algorithm**: Optimized sharpness calculation for faster convergence
- **Multi-Camera Support**: Better handling of concurrent camera operations
