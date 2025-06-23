# focus_script.py
# Location: ~/space/ros2_ws/src/focus_control/focus_control/focus_script.py

import rclpy
from rclpy.node import Node
from std_msgs.msg import String
from std_srvs.srv import Trigger
import subprocess
import json
import os
import signal


class FocusControl(Node):
    def __init__(self):
        super().__init__('focus_control')

        self.create_service(Trigger, 'start_focusing', self.start_focusing_service)
        self.create_service(Trigger, 'stop_focusing', self.stop_focusing_service)
        self.create_subscription(String, 'set_camera', self.set_camera_callback, 10)

        self.focus_process = None
        self.camera_id = None
        self.lens_spec = "2.8mm"
        self.focus_distance = 1000  # Default to 1 meter
        
        # Create timer to periodically check and clean up completed processes
        self.cleanup_timer = self.create_timer(2.0, self.cleanup_completed_process)

    def cleanup_completed_process(self):
        """Automatically clean up completed focus processes"""
        if self.focus_process is not None:
            poll_result = self.focus_process.poll()
            if poll_result is not None:
                # Process has completed (either success or failure)
                if poll_result == 0:
                    self.get_logger().info("✅ Focus process completed successfully, cleaning up")
                else:
                    self.get_logger().warning(f"⚠️ Focus process finished with exit code {poll_result}, cleaning up")
                self.focus_process = None

    def set_camera_callback(self, msg):
        try:
            self.camera_id = int(msg.data)
            self.get_logger().info(f"📸 Camera set to: {self.camera_id}")
        except ValueError:
            self.get_logger().error("❌ Invalid camera ID")

    def start_focusing_service(self, request, response):
        self.get_logger().info("🚀 Received start_focusing service call")

        # Force cleanup of any completed process first
        self.cleanup_completed_process()
        
        if self.focus_process is None:
            # Check if session config exists (created by Flask)
            config_path = "/tmp/focus_session.json"
            config = None
            
            try:
                if os.path.exists(config_path):
                    with open(config_path, "r") as f:
                        config = json.load(f)
                    self.get_logger().info(f"📖 Loaded session config: {config}")
                else:
                    self.get_logger().warning("⚠️ No session config found, using fallback values")
            except Exception as e:
                self.get_logger().error(f"❌ Failed to read session config: {e}")

            # Use config from file if available, otherwise fall back to internal state
            if config and config.get("camera_id") is not None:
                camera_id = config["camera_id"]
                lens_spec = config.get("lens_spec", self.lens_spec)
                focus_distance = config.get("focus_distance", self.focus_distance)
                calibration_mode = config.get("calibration_mode", False)
            elif self.camera_id is not None:
                # Fallback to topic-based camera selection
                camera_id = self.camera_id
                lens_spec = self.lens_spec
                focus_distance = self.focus_distance
                calibration_mode = False
            else:
                self.get_logger().error("❌ No camera selected via config or topic.")
                response.success = False
                response.message = "No camera selected."
                return response

            # Update config with determined values
            config = {
                "camera_id": camera_id,
                "lens_spec": lens_spec,
                "focus_distance": focus_distance,
                "calibration_mode": calibration_mode
            }

            config_path = "/tmp/focus_session.json"
            try:
                with open(config_path, "w") as f:
                    json.dump(config, f)
                self.get_logger().info(f"✅ Session config written to {config_path}")
            except Exception as e:
                self.get_logger().error(f"❌ Failed to write session config: {e}")
                response.success = False
                response.message = "Failed to write session config."
                return response

            env_script = "/home/ubuntu/space/ros2_ws/install/setup.bash"
            focus_runner_path = "/home/ubuntu/space/ros2_ws/src/focus_control/focus_control/focus_runner.py"
            launch_script_path = "/tmp/focus_launcher.sh"
            log_file = "/tmp/focus_runner_output.txt"

            try:
                with open(launch_script_path, "w") as script_file:
                    script_file.write(f"""#!/bin/bash
# Set up display environment for GUI applications
export DISPLAY=:0
export XDG_RUNTIME_DIR=/run/user/1000
export XDG_SESSION_TYPE=x11
export XAUTHORITY=/home/ubuntu/.Xauthority
export HOME=/home/ubuntu
export USER=ubuntu

# Source ROS2 environment but use system Python to avoid NumPy conflicts
source {env_script}
echo "✅ ENV SET (with display), now running focus_runner"

# Use venv Python3 which now has GStreamer-enabled OpenCV
/space/projects/project_icarus/venv/bin/python3 {focus_runner_path} > {log_file} 2>&1
""")
                os.chmod(launch_script_path, 0o755)
                self.get_logger().info(f"✅ Launcher script written to {launch_script_path}")
            except Exception as e:
                self.get_logger().error(f"❌ Failed to write launcher script: {e}")
                response.success = False
                response.message = "Failed to write launcher script."
                return response

            try:
                self.focus_process = subprocess.Popen(
                    ["/bin/bash", launch_script_path],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    start_new_session=True
                )
                self.get_logger().info(f"🚀 focus_runner launched as isolated process (PID: {self.focus_process.pid}), logging to {log_file}")
                response.success = True
                response.message = "Focus session started."
            except Exception as e:
                self.get_logger().error(f"❌ Failed to launch focus_runner: {e}")
                # Ensure we don't leave a hanging process reference
                self.focus_process = None
                response.success = False
                response.message = "Failed to launch focus_runner."
        else:
            response.success = False
            response.message = "Focus already running."

        return response

    def stop_focusing_service(self, request, response):
        if self.focus_process and self.focus_process.poll() is None:
            self.get_logger().info(f"🛑 Stopping focus session (PID: {self.focus_process.pid})...")
            try:
                # Send SIGINT to entire process group
                os.killpg(os.getpgid(self.focus_process.pid), signal.SIGINT)
                self.focus_process.wait(timeout=10)
                self.get_logger().info("✅ Focus process stopped gracefully")
                response.success = True
                response.message = "Focus session stopped."
            except subprocess.TimeoutExpired:
                self.get_logger().warning("⚠️ Focus process didn't stop gracefully, force killing...")
                try:
                    os.killpg(os.getpgid(self.focus_process.pid), signal.SIGKILL)
                except ProcessLookupError:
                    pass  # Process already dead
                response.success = False
                response.message = "Force killed hanging focus process."
            except ProcessLookupError:
                # Process already dead
                self.get_logger().info("✅ Focus process already terminated")
                response.success = True
                response.message = "Focus session already stopped."
            self.focus_process = None
        else:
            response.success = False
            response.message = "No focus session running."

        return response


def main(args=None):
    rclpy.init(args=args)
    node = FocusControl()
    rclpy.spin(node)
    node.destroy_node()
    rclpy.shutdown()


if __name__ == '__main__':
    main()

