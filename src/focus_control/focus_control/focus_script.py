# focus_script.py
# Location: ~/space/ros2_ws/src/focus_control/focus_control/focus_script.py

import rclpy
from rclpy.node import Node
from std_msgs.msg import String
from std_srvs.srv import Trigger
import json
import os
import threading
import time
from datetime import datetime
import logging

# Suppress matplotlib font manager debug logs
logging.getLogger('matplotlib.font_manager').setLevel(logging.WARNING)

from focus_control.focus_session import FocusSession
from focus_control.focus_plotter import FocusPlotter


class FocusControl(Node):
    def __init__(self):
        super().__init__('focus_control')

        self.create_service(Trigger, 'start_focusing', self.start_focusing_service)
        self.create_service(Trigger, 'stop_focusing', self.stop_focusing_service)
        self.create_subscription(String, 'set_camera', self.set_camera_callback, 10)

        # Replace subprocess with direct focus session management
        self.focus_session = None
        self.focus_thread = None
        self.camera_id = None
        self.lens_spec = "2.8mm"
        self.focus_distance = 1000  # Default to 1 meter
        self.emergency_stop_requested = False  # Track if emergency stop was requested
        
        # Create publishers for focus events (moved from focus_runner)
        self.score_pub = self.create_publisher(String, "focus_score", 10)
        self.annotation_pub = self.create_publisher(String, "focus_annotation", 10)
        self.focus_done_pub = self.create_publisher(String, "focus_complete", 10)
        self.focus_start_pub = self.create_publisher(String, "focus_start", 10)
        
        # Create motor command publishers for emergency cleanup
        self.motor_command_pub = self.create_publisher(String, "motor_command", 10)
        self.scripted_command_pub = self.create_publisher(String, "scripted_motor_command", 10)
        
        # Create timer to periodically check and clean up completed focus sessions
        self.cleanup_timer = self.create_timer(2.0, self.cleanup_completed_session)

    def cleanup_completed_session(self):
        """Automatically clean up completed focus sessions"""
        if self.focus_thread is not None and not self.focus_thread.is_alive():
            self.get_logger().info("Focus session thread completed, cleaning up")
            self.focus_thread = None
            if self.focus_session:
                # Release camera resources
                try:
                    self.focus_session.release_camera()
                except Exception as e:
                    self.get_logger().error(f"Error releasing camera: {e}")
                # CRITICAL: Set to None to ensure fresh instance on next run
                self.focus_session = None
                self.get_logger().info("Focus session object cleared for next run")

    def set_camera_callback(self, msg):
        try:
            self.camera_id = int(msg.data)
            self.get_logger().info(f"📸 Camera set to: {self.camera_id}")
        except ValueError:
            self.get_logger().error("❌ Invalid camera ID")

    def start_focusing_service(self, request, response):
        self.get_logger().info("🚀 Received start_focusing service call")

        # Force cleanup of any completed session first
        self.cleanup_completed_session()
        
        # If there's an existing focus_session object, ensure it's properly cleaned up
        if self.focus_session is not None:
            self.get_logger().info("🧹 Cleaning up existing focus session before starting new one")
            try:
                self.focus_session.release_camera()
            except Exception as e:
                self.get_logger().error(f"Error releasing camera from previous session: {e}")
            self.focus_session = None
        
        self.get_logger().info(f"🔍 Focus thread state: {self.focus_thread is not None}, alive: {self.focus_thread.is_alive() if self.focus_thread else 'N/A'}")
        
        if self.focus_thread is None or not self.focus_thread.is_alive():
            self.get_logger().info("✅ Starting new focus session")
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

            # Reset emergency stop flag for new session
            self.emergency_stop_requested = False
            
            # Create focus session directly (no subprocess needed)
            try:
                plotter = FocusPlotter()
                self.focus_session = FocusSession(
                    node=self,
                    score_publisher=self.score_pub,
                    annotation_publisher=self.annotation_pub,
                    plotter=plotter,
                    camera_id=camera_id,
                    lens_spec=lens_spec,
                    focus_distance=focus_distance,
                    focus_done_publisher=self.focus_done_pub,
                    focus_start_publisher=self.focus_start_pub
                )
                
                # Start focus session in a background thread
                self.focus_thread = threading.Thread(
                    target=self._run_focus_session,
                    args=(calibration_mode,),
                    daemon=True
                )
                self.focus_thread.start()
                
                self.get_logger().info(f"Focus session started directly on camera {camera_id}")
                response.success = True
                response.message = "Focus session started."
                
            except Exception as e:
                self.get_logger().error(f"Failed to start focus session: {e}")
                self.focus_session = None
                response.success = False
                response.message = f"Failed to start focus session: {str(e)}"
        else:
            self.get_logger().warning(f"❌ Focus already running - thread alive: {self.focus_thread.is_alive()}")
            response.success = False
            response.message = "Focus already running."

        return response

    def _run_focus_session(self, calibration_mode):
        """Run the focus session in a background thread (replaces focus_runner subprocess)"""
        try:
            self.get_logger().info("🚀 Focus session thread started")
            
            # Set servo to home position initially
            self.get_logger().info("🔧 Setting servo to home position")
            try:
                self.focus_session.set_servo_position(self.focus_session.servo_support_home)
                self.get_logger().info("✅ Servo position set successfully")
            except Exception as e:
                self.get_logger().warn(f"⚠️ Failed to set servo position: {e}, continuing anyway")
            
            # Publish focus start event
            self.get_logger().info("📢 Publishing focus start event")
            self.focus_start_pub.publish(String(data=json.dumps({
                "timestamp": datetime.now().isoformat(),
                "camera_id": self.focus_session.camera_id,
                "lens_spec": self.focus_session.lens_spec,
                "focus_distance": self.focus_session.focus_distance,
                "calibration_mode": calibration_mode
            })))
            
            if calibration_mode:
                self.get_logger().info("🔧 Running Lens Calibration")
                self.focus_session.run_calibration()
                label = "calibration"
                log_subdir = "calibration_logs"
            else:
                self.get_logger().info("🎯 About to start Auto-Focus Session")
                self.focus_session.run_focus_loop()
                self.get_logger().info("✅ Auto-Focus Session completed")
                label = "focus"
                log_subdir = "process_logs"

            # Save graph after session
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            graph_dir = f"/home/ubuntu/focus_logs/{log_subdir}/graphs"
            os.makedirs(graph_dir, exist_ok=True)

            # Get serial number from session if available
            serial_number = getattr(self.focus_session, 'current_serial_number', '')
            if serial_number:
                graph_filename = f"{label}_graph_{serial_number}_{self.focus_session.lens_spec}_{self.focus_session.focus_distance}mm_cam{self.focus_session.camera_id}_{timestamp}.png"
            else:
                graph_filename = f"{label}_graph_{self.focus_session.lens_spec}_{self.focus_session.focus_distance}mm_cam{self.focus_session.camera_id}_{timestamp}.png"
                
            plot_path = os.path.join(graph_dir, graph_filename)
            try:
                self.focus_session.plotter.save_graph(plot_path)
                self.get_logger().info(f"Graph saved to: {plot_path}")
            except Exception as e:
                self.get_logger().warning(f"Failed to save graph: {e}")

        except Exception as e:
            self.get_logger().error(f"Focus session failed: {e}")
        finally:
            self.get_logger().info("🔄 Focus thread entering cleanup...")
            
            # Always publish focus_complete for UI reset
            self.focus_done_pub.publish(String(data="done"))
            self.get_logger().info("📢 Published focus_complete message")
            
            # Only do normal cleanup if emergency stop wasn't requested
            if not self.emergency_stop_requested:
                # Clear Nano queue before shutdown
                from rclpy.qos import QoSProfile
                queue_pub = self.create_publisher(String, 'clear_scripted_queue', QoSProfile(depth=1))
                queue_pub.publish(String(data="clear"))
                time.sleep(0.2)
                self.get_logger().info("Queue clear command sent to Nano")

                # Normal cleanup session resources
                if self.focus_session:
                    self.focus_session.cleanup()
                self.get_logger().info("Focus session complete")
            else:
                self.get_logger().info("Emergency stop requested - skipping normal cleanup")
                # Still release camera on emergency stop
                if self.focus_session:
                    try:
                        self.focus_session.release_camera()
                    except Exception as e:
                        self.get_logger().error(f"Error releasing camera during emergency stop: {e}")
            
            self.get_logger().info("🏁 Focus thread cleanup completed")

    def _emergency_cleanup_motors(self):
        """Emergency motor cleanup using service node publishers (more reliable)"""
        try:
            # Step 1: Signal session to stop FIRST
            if self.focus_session:
                self.focus_session.shutdown_event.set()
            
            # Step 2: Clear any queued commands
            self.get_logger().info("📍 Step 1: Clearing motor queue")
            from rclpy.qos import QoSProfile
            queue_clear_pub = self.create_publisher(String, 'clear_scripted_queue', QoSProfile(depth=1))
            queue_clear_pub.publish(String(data="clear"))
            time.sleep(1.0)
            
            # Step 3: Lift ZA by 5mm for safety (direct command)
            self.get_logger().info("📍 Step 2: Lifting ZA by 5mm for safety")
            self.get_logger().info("🤖 Publishing: M ZA 16000 0")
            self.motor_command_pub.publish(String(data="M ZA 16000 0"))
            time.sleep(4.0)  # Extra time for lift
            
            # Step 4: Move servo to home position (direct command)  
            self.get_logger().info("📍 Step 3: Moving servo to home position")
            self.get_logger().info("🤖 Publishing: S 120")
            self.motor_command_pub.publish(String(data="S 120"))
            time.sleep(3.0)  # Extra time for servo
            
            # Step 5: Home ZA axis (direct command)
            self.get_logger().info("📍 Step 4: Homing ZA axis")
            self.get_logger().info("🤖 Publishing: H ZA")
            self.motor_command_pub.publish(String(data="H ZA"))
            time.sleep(8.0)  # Extra time for homing operation
            
            self.get_logger().info("✅ Emergency motor cleanup complete")
            
        except Exception as e:
            self.get_logger().error(f"❌ Error during emergency motor cleanup: {e}")

    def stop_focusing_service(self, request, response):
        if self.focus_thread and self.focus_thread.is_alive():
            self.get_logger().info("🛑 Stopping focus session...")
            try:
                # Set emergency stop flag so the thread knows to skip normal cleanup
                self.emergency_stop_requested = True
                
                # Perform emergency cleanup FIRST using service node publishers
                self.get_logger().info("🚨 Performing emergency cleanup...")
                self._emergency_cleanup_motors()
                
                # Wait for thread to complete after cleanup
                self.get_logger().info("⏱️ Waiting for focus thread to complete...")
                self.focus_thread.join(timeout=15.0)  # Increased timeout for cleanup
                
                if self.focus_thread.is_alive():
                    self.get_logger().warning("⚠️ Focus session thread didn't stop gracefully")
                    response.success = False
                    response.message = "Focus session didn't stop gracefully."
                else:
                    self.get_logger().info("✅ Focus session stopped with emergency cleanup")
                    response.success = True
                    response.message = "Focus session stopped safely."
                    
                # Clean up resources
                if self.focus_session:
                    # Ensure camera is released even in emergency stop
                    try:
                        if hasattr(self.focus_session, 'cap') and self.focus_session.cap:
                            self.focus_session.release_camera()
                    except Exception as e:
                        self.get_logger().error(f"Error releasing camera in stop service: {e}")
                    self.focus_session = None
                self.focus_thread = None
                self.emergency_stop_requested = False  # Reset flag
                
            except Exception as e:
                self.get_logger().error(f"❌ Error stopping focus session: {e}")
                response.success = False
                response.message = f"Error stopping focus session: {str(e)}"
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

