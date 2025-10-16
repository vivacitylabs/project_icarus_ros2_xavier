import os
import sys
import json
import threading
from datetime import datetime
import time
import logging

# Suppress matplotlib font manager debug logs
logging.getLogger('matplotlib.font_manager').setLevel(logging.WARNING)

import rclpy
from rclpy.node import Node
from std_msgs.msg import String

from focus_control.focus_session import FocusSession
from focus_control.focus_plotter import FocusPlotter


def load_session_config(path="/tmp/focus_session.json"):
    if not os.path.exists(path):
        print("⚠️ No session config found. Using defaults.")
        print("⚙️ camera_id=0, lens=2.8mm, distance=1000mm, calibration_mode=False")
        if os.isatty(0):  # interactive terminal
            try:
                input("Press Enter to continue or Ctrl+C to cancel...")
            except KeyboardInterrupt:
                print("\n❌ Aborted.")
                exit(1)
        return {
            "camera_id": 0,
            "lens_spec": "2.8mm",
            "focus_distance": 1000,
            "calibration_mode": False
        }
    else:
        with open(path, "r") as f:
            return json.load(f)


def main():
    config = load_session_config()
    camera_id = config["camera_id"]
    lens_spec = config["lens_spec"]
    focus_distance = config["focus_distance"]
    calibration_mode = config.get("calibration_mode", False)

    rclpy.init()
    node = Node("focus_runner")
    node.get_logger().set_level(rclpy.logging.LoggingSeverity.DEBUG)

    # Spin ROS2 on a background thread so subscriptions work
    spin_thread = threading.Thread(target=rclpy.spin, args=(node,), daemon=True)
    spin_thread.start()

    score_pub = node.create_publisher(String, "focus_score", 10)
    annotation_pub = node.create_publisher(String, "focus_annotation", 10)
    focus_done_pub = node.create_publisher(String, "focus_complete", 10)
    focus_start_pub = node.create_publisher(String, "focus_start", 10)

    plotter = FocusPlotter()

    session = FocusSession(
        node=node,
        score_publisher=score_pub,
        annotation_publisher=annotation_pub,
        plotter=plotter,
        camera_id=camera_id,
        lens_spec=lens_spec,
        focus_distance=focus_distance,
        focus_done_publisher=focus_done_pub,
        focus_start_publisher=focus_start_pub
    )

    # Camera will be initialized lazily when focus operations begin
    node.get_logger().info("🚀 Focus service ready - camera will be initialized when needed")

    # ✅ Default pre-move servo position (optional)
    session.set_servo_position(session.servo_support_home)

    try:
        if calibration_mode:
            node.get_logger().info("🔧 Running Lens Calibration")
            session.run_calibration()
            label = "calibration"
            log_subdir = "calibration_logs"
        else:
            node.get_logger().info("🎯 Running Auto-Focus Session")
            session.run_focus_loop()
            label = "focus"
            log_subdir = "process_logs"

        # ✅ Save graph after session
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        graph_dir = f"/home/ubuntu/focus_logs/{log_subdir}/graphs"
        os.makedirs(graph_dir, exist_ok=True)

        # Get serial number from session if available
        serial_number = getattr(session, 'current_serial_number', '')
        if serial_number:
            graph_filename = f"{label}_graph_{serial_number}_{lens_spec}_{focus_distance}mm_cam{camera_id}_{timestamp}.png"
        else:
            graph_filename = f"{label}_graph_{lens_spec}_{focus_distance}mm_cam{camera_id}_{timestamp}.png"
            
        plot_path = os.path.join(graph_dir, graph_filename)
        plotter.save_graph(plot_path)
        node.get_logger().info(f"📊 Graph saved to: {plot_path}")

    finally:
        # ✅ Flush Nano queue before shutdown
        from rclpy.qos import QoSProfile
        from std_msgs.msg import String as StringMsg
        queue_pub = node.create_publisher(StringMsg, 'clear_scripted_queue', QoSProfile(depth=1))
        queue_pub.publish(StringMsg(data="clear"))
        time.sleep(0.2)
        node.get_logger().info("🧹 Queue clear command sent to Nano")

        session.cleanup()
        node.destroy_node()
        rclpy.shutdown()
        node.get_logger().info("✅ focus_runner.py complete.")


if __name__ == "__main__":
    main()

