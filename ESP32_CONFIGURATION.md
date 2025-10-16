# ESP32 Motor Controller Configuration

## System Overview
The motor control system uses an ESP32 microcontroller connected via USB serial to the Jetson Nano, which bridges commands from the Xavier via ROS2.

## Hardware Configuration

### ESP32 Connection
- **Device**: ESP32 with CP210x UART Bridge (Silicon Labs)
- **USB Vendor ID**: `10c4`
- **USB Product ID**: `ea60`
- **Serial Device**: `/dev/teensy` (udev symlink)
- **Baud Rate**: **115200** (IMPORTANT: Must match ESP32 firmware)

### Connection Chain
```
Xavier AGX → Ethernet → Jetson Nano → USB Serial → ESP32 → Motor Drivers
```

## Critical Configuration Files

### 1. udev Rule (Jetson Nano)
**Location**: `/etc/udev/rules.d/99-teensy.rules`

**Content**:
```
SUBSYSTEM=="tty", ATTRS{idVendor}=="10c4", ATTRS{idProduct}=="ea60", SYMLINK+="teensy", MODE="0666"
```

**Purpose**: Creates a persistent `/dev/teensy` symlink that automatically follows the ESP32 regardless of which USB port (ttyUSB0, ttyUSB1, etc.) it gets assigned.

**Reload after changes**:
```bash
sudo udevadm control --reload-rules
sudo udevadm trigger
```

### 2. Serial Node Configuration (Jetson Nano)
**Source**: `/home/jetson/ros2_ws/src/teensy_serial/teensy_serial/teensy_serial_node.py`

**Key Settings**:
```python
self.serial_port = '/dev/teensy'
self.baud_rate = 115200  # MUST match ESP32 firmware
self.reconnect_delay = 2.0
self.max_reconnect_attempts = 3
```

**After code changes**:
```bash
cd /home/jetson/ros2_ws
rm -rf build/teensy_serial install/teensy_serial
source /opt/ros/foxy/setup.bash
colcon build --packages-select teensy_serial
sudo systemctl restart teensy_serial_node.service
```

### 3. systemd Service (Jetson Nano)
**Location**: `/etc/systemd/system/teensy_serial_node.service`

**Content**:
```ini
[Unit]
Description=Teensy Serial Node (ROS 2)
After=network.target
StartLimitIntervalSec=0

[Service]
User=jetson
WorkingDirectory=/home/jetson/ros2_ws
ExecStartPre=/bin/sleep 5
ExecStart=/bin/bash -c 'source /opt/ros/foxy/setup.bash && source install/setup.bash && ros2 run teensy_serial teensy_serial_node'
Restart=always
RestartSec=5
Environment="ROS_DOMAIN_ID=0"

[Install]
WantedBy=multi-user.target
```

**Important settings**:
- `ExecStartPre=/bin/sleep 5` - Waits for ESP32 to fully boot
- `Restart=always` - Auto-restarts on any failure
- `RestartSec=5` - Waits 5 seconds before restart

**After service file changes**:
```bash
sudo systemctl daemon-reload
sudo systemctl restart teensy_serial_node.service
```

## Robustness Features

### Automatic Reconnection
The serial node now includes:
- **Retry logic**: 3 attempts with 2-second delays on initial connection
- **Health monitoring**: Checks connection every 5 seconds
- **Automatic recovery**: Reconnects on I/O errors or disconnections
- **Error tracking**: Triggers reconnection after 5 consecutive errors

### Boot Message Filtering
ESP32 boot messages (containing `rst:`, `ets`, `boot:`, `invalid header`) are automatically filtered out and logged as warnings instead of errors.

### Graceful Degradation
- Commands queued while disconnected won't crash the system
- Service auto-restarts if process crashes
- Status published to ROS2 topics for monitoring

## Troubleshooting

### Motors not responding after reboot

1. **Check ESP32 connection**:
   ```bash
   ssh jetson@192.168.0.2
   lsusb | grep Silicon
   ls -la /dev/teensy
   ```

2. **Check service status**:
   ```bash
   sudo systemctl status teensy_serial_node.service
   sudo journalctl -u teensy_serial_node.service -n 20
   ```

3. **Look for connection message**:
   ```
   ✅ Connected to ESP32 via /dev/teensy at 115200 baud
   ```

4. **Test command manually**:
   ```bash
   # From Xavier:
   ros2 topic pub --once /motor_command std_msgs/msg/String "data: 'H B'"
   ```

### ESP32 stuck in boot loop

**Symptoms**: Logs show repeated `rst:0x10 (RTCWDT_RTC_RESET)` messages

**Solution**: ESP32 firmware is crashing. Power cycle the ESP32:
```bash
# Unplug and replug ESP32 USB cable, or:
ssh jetson@192.168.0.2
sudo reboot
```

### Baud rate mismatch

**Symptoms**: Commands sent but no responses received

**Check baud rates match**:
1. ESP32 firmware serial initialization: Should be `Serial.begin(115200)`
2. Serial node configuration: `self.baud_rate = 115200`
3. No stale builds cached: Always rebuild after changing baud rate

### Permission denied errors

**Symptoms**: `❌ Failed to connect: [Errno 13] Permission denied`

**Solution**: Add user to dialout group:
```bash
ssh jetson@192.168.0.2
sudo usermod -a -G dialout jetson
# Reboot or restart service
```

## Testing Commands

### Test ROS2 topics:
```bash
# List topics
ros2 topic list | grep motor

# Send homing command
ros2 topic pub --once /motor_command std_msgs/msg/String "data: 'H XY'"

# Send movement command
ros2 topic pub --once /motor_command std_msgs/msg/String "data: 'M B 100 0'"

# Monitor responses
ros2 topic echo /motor_ack
```

### Monitor serial communication:
```bash
ssh jetson@192.168.0.2
sudo journalctl -u teensy_serial_node.service -f
```

## Maintenance Checklist

### After Xavier reboot:
- [ ] Verify ROS2 focus node running: `systemctl status ros2_focus_node.service`
- [ ] Check motor topics exist: `ros2 topic list | grep motor`
- [ ] Test command from Xavier to ESP32

### After Nano reboot:
- [ ] Verify ESP32 connected: `lsusb | grep Silicon`
- [ ] Verify serial node running: `systemctl status teensy_serial_node.service`
- [ ] Check for connection log: `journalctl -u teensy_serial_node.service -n 10`
- [ ] Test motor command

### After ESP32 reconnection:
- [ ] Service should auto-restart within 5 seconds
- [ ] Check logs for successful connection
- [ ] Test motor command

## Version History

- **2025-10-10**: Enhanced with automatic reconnection, health monitoring, boot message filtering
- **2025-10-08**: Updated from Teensy 4.1 to ESP32, changed baud from 921600 to 115200
- **Initial**: System designed for Teensy 4.1 at 921600 baud
