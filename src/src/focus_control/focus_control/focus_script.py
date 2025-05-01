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

    def set_camera_callback(self, msg):
        try:
            self.camera_id = int(msg.data)
            self.get_logger().info(f"📸 Camera set to: {self.camera_id}")
        except ValueError:
            self.get_logger().error("❌ Invalid camera ID")

    def start_focusing_service(self, request, response):
        self.get_logger().info("🚀 Received start_focusing service call")

        if self.focus_process is None or self.focus_process.poll() is not None:
            if self.camera_id is None:
                self.get_logger().error("❌ No camera selected.")
                response.success = False
                response.message = "No camera selected."
                return response

            config = {
                "camera_id": self.camera_id,
                "lens_spec": self.lens_spec,
                "focus_distance": self.focus_distance
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
source {env_script}
echo "✅ ENV SET, now running focus_runner"
python3 {focus_runner_path} > {log_file} 2>&1
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
                    ["nohup", "/bin/bash", launch_script_path],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    preexec_fn=os.setsid
                )
                self.get_logger().info(f"🚀 focus_runner launched with nohup, logging to {log_file}")
                response.success = True
                response.message = "Focus session started."
            except Exception as e:
                self.get_logger().error(f"❌ Failed to launch focus_runner: {e}")
                response.success = False
                response.message = "Failed to launch focus_runner."
        else:
            response.success = False
            response.message = "Focus already running."

        return response

    def stop_focusing_service(self, request, response):
        if self.focus_process and self.focus_process.poll() is None:
            self.get_logger().info("🛑 Stopping focus session...")
            self.focus_process.send_signal(signal.SIGINT)
            try:
                self.focus_process.wait(timeout=10)
                response.success = True
                response.message = "Focus session stopped."
            except subprocess.TimeoutExpired:
                self.focus_process.kill()
                response.success = False
                response.message = "Force killed hanging focus process."
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

