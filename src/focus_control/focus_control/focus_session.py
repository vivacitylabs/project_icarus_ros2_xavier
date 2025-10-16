# focus_session.py
# Location: ~/space/ros2_ws/src/focus_control/focus_control/focus_session.py

# Force use of working system OpenCV with GStreamer support
import sys
sys.path.insert(0, '/usr/lib/python3/dist-packages')

import cv2
import csv
import time
import os
POSITIONS_PATH = "/home/ubuntu/space/projects/project_icarus/positions.json"
CURRENT_POS_PATH = "/home/ubuntu/space/projects/project_icarus/current_position.json"

# import glfw  # Removed - using OpenCV display instead
import json
import numpy as np
import threading
from datetime import datetime
from std_msgs.msg import String
import moderngl
from .focus_positions_config import FocusPositionsConfig

def load_json(path):
    with open(path, 'r') as f:
        return json.load(f)

def save_json(path, data):
    with open(path, 'w') as f:
        json.dump(data, f, indent=2)

def load_lens_config():
    """Load lens configuration from JSON file, with fallback to defaults"""
    config_path = "/space/ros2_ws/lens_config.json"
    try:
        if os.path.exists(config_path):
            with open(config_path, 'r') as f:
                config = json.load(f)
                return config.get('lens_profiles', {}), config.get('default_settings', {}), config.get('global_settings', {})
        else:
            print(f"Warning: Lens config file not found at {config_path}, using defaults")
            return {}, {}, {}
    except Exception as e:
        print(f"Error loading lens config: {e}, using defaults")
        return {}, {}, {}

def get_next_serial_number():
    """Get the next available serial number and increment the counter"""
    serial_file = "/home/ubuntu/focus_logs/serial_counter.json"
    os.makedirs(os.path.dirname(serial_file), exist_ok=True)
    
    try:
        if os.path.exists(serial_file):
            with open(serial_file, 'r') as f:
                data = json.load(f)
                current_sn = data.get('last_serial_number', 0)
        else:
            current_sn = 0
    except:
        current_sn = 0
    
    # Increment and save
    next_sn = current_sn + 1
    with open(serial_file, 'w') as f:
        json.dump({
            'last_serial_number': next_sn,
            'last_updated': datetime.now().isoformat()
        }, f, indent=2)
    
    return f"SN{next_sn:06d}"  # Format as SN000001, SN000002, etc.
        
class FocusSession:
    def __init__(self, node, score_publisher, plotter, camera_id, lens_spec, focus_distance, annotation_publisher=None, focus_done_publisher=None, focus_start_publisher=None):
        self.node = node
        self.logger = node.get_logger()  # Initialize logger from ROS2 node
        self.cap = None
        self.latest_frame = None
        self.shutdown_event = threading.Event()
        self.frame_lock = threading.Lock()
        self.frame_ready = threading.Event()

        # Add proper camera resource management
        self.camera_initialized = False
        self.camera_lock = threading.Lock()

        # Initialize focus positions configuration
        self.focus_config = FocusPositionsConfig()

        self.scripted_pub = self.node.create_publisher(String, 'scripted_motor_command', 10)
        self.direct_pub = self.node.create_publisher(String, 'motor_command', 10)

        self.ack_event = threading.Event()
        self.node.create_subscription(String, 'motor_ack', self.motor_ack_callback, 10)

        self.score_publisher = score_publisher
        self.plotter = plotter
        self.camera_id = camera_id
        self.lens_spec = lens_spec
        self.focus_distance = focus_distance

        self.positions = []
        self.scores = []
        self.current_score = 0.0
        self.current_phase = "idle"
        self.annotation_publisher = annotation_publisher
        self.focus_done_publisher = focus_done_publisher
        self.focus_start_publisher = focus_start_publisher

        self.plot_lock = threading.Lock()

        # Get servo positions from config
        servo_positions = self.focus_config.get_servo_positions()
        self.servo_support_active = servo_positions['active']
        self.servo_support_home = servo_positions['home']
        
        # Load lens configuration from file
        lens_profiles, default_settings, global_settings = load_lens_config()
        self.config_last_modified = 0
        self.config_path = "/space/ros2_ws/lens_config.json"
        self.global_settings = global_settings
        
        # Use loaded config or fall back to hardcoded defaults
        if lens_profiles:
            self.lens_focus_configs = lens_profiles
            self.node.get_logger().info(f"✅ Loaded lens configuration from {self.config_path}")
        else:
            self.node.get_logger().info("⚠️ Using hardcoded lens configuration")
            self.lens_focus_configs = {
            "2.8mm": {
                "roi_radius_ratio": 0.45,
                "initial_step": 250,
                "micro_steps": [18, 10, 2],
                "ultra_micro_steps": [6, 1],
                "spike_threshold": 8.0,
                "entry_multiplier": 4.6,
                "early_spike_delta": 70.0,
                "post_reversal_grace": 5,
                "settle_delay_micro": 0.2,
                "settle_delay_ultra": 0.6,
            },
            "4mm": {
                "roi_radius_ratio": 0.42,
                "initial_step": 450,
                "micro_steps": [25, 18, 15],
                "ultra_micro_steps": [4, 1],
                "spike_threshold": 8.0,
                "entry_multiplier": 4.0,
                "early_spike_delta": 80.0,
                "post_reversal_grace": 4,
                "settle_delay_micro": 0.25,
                "settle_delay_ultra": 0.7,
            },
            "6mm": {
                "roi_radius_ratio": 0.44,
                "initial_step": 350,
                "micro_steps": [30, 20, 15],
                "ultra_micro_steps": [5, 1],
                "spike_threshold": 5.0,
                "entry_multiplier": 2.5,
                "early_spike_delta": 60.0,
                "post_reversal_grace": 4,
                "settle_delay_micro": 0.3,
                "settle_delay_ultra": 0.65,
            },
            "8mm": {
                "roi_radius_ratio": 0.60,
                "initial_step": 350,
                "micro_steps": [40, 25, 10],
                "ultra_micro_steps": [2, 1],
                "spike_threshold": 4.0,
                "entry_multiplier": 8.0,
                "early_spike_delta": 80.0,
                "post_reversal_grace": 4,
                "settle_delay_micro": 0.4,
                "settle_delay_ultra": 0.8,
            },
            "12mm": {
                "roi_radius_ratio": 0.28,
                "initial_step": 600,
                "micro_steps": [40, 20, 10],
                "ultra_micro_steps": [4, 1],
                "spike_threshold": 1.5,
                "entry_multiplier": 1.8,
                "early_spike_delta": 12.0,
                "post_reversal_grace": 4,
                "settle_delay_micro": 0.4,
                "settle_delay_ultra": 0.75,
            },
            "16mm": {
                "roi_radius_ratio": 0.28,
                "initial_step": 600,
                "micro_steps": [40, 20, 10],
                "ultra_micro_steps": [4, 1],
                "spike_threshold": 1.3,
                "entry_multiplier": 1.8,
                "early_spike_delta": 10.0,
                "post_reversal_grace": 4,
                "settle_delay_micro": 0.45,
                "settle_delay_ultra": 0.8,
            },
            "25mm": {
                "roi_radius_ratio": 0.28,
                "initial_step": 600,
                "micro_steps": [30, 20, 10],
                "ultra_micro_steps": [3, 1],
                "spike_threshold": 1.2,
                "entry_multiplier": 1.5,
                "early_spike_delta": 8.0,
                "post_reversal_grace": 3,
                "settle_delay_micro": 0.5,
                "settle_delay_ultra": 0.85,
            }
        }




    def run_pre_focus_sequence(self):
        self.node.get_logger().info("🔧 Running pre-focus sequence")
        self.send_annotation("phase", 0, "pre_focus")

        positions = load_json(POSITIONS_PATH)
        current = load_json(CURRENT_POS_PATH)

        # === FIRST: Position B-axis to camera BEFORE any other movements ===
        self.node.get_logger().info("🎯 STEP 1: Positioning B-axis for camera module FIRST")
        try:
            # Get camera position from focus config
            camera_b_position = self.focus_config.get_camera_position(self.camera_id)
            if camera_b_position is not None:
                self.safe_b_axis_move(self.camera_id)
                # Update position tracking
                current["positions"]["B"]["B"] = camera_b_position
                self.node.get_logger().info(f"✅ B-axis positioned for Camera{self.camera_id} at {camera_b_position}mm")
            else:
                self.node.get_logger().warn(f"⚠️ No configured B position for Camera{self.camera_id}")
        except Exception as e:
            self.node.get_logger().warn(f"⚠️ Failed to position B axis: {e}, continuing anyway")

        # === SECOND: Home ZA after B-axis is in position ===
        self.node.get_logger().info("🏠 STEP 2: Homing ZA (B-axis already positioned)")
        try:
            self.send_motor_command("H ZA", scripted=False)
            time.sleep(2.0)
            current["positions"]["ZA"]["Z"] = 0.0
            current["positions"]["ZA"]["A"] = 0.0
        except Exception as e:
            self.node.get_logger().warn(f"⚠️ Failed to home ZA: {e}, continuing anyway")

        # === THIRD: Servo to ACTIVE (raise to hold lens) FIRST ===
        self.node.get_logger().info("🤖 STEP 3: Raising servo to active position")
        try:
            for angle in [40, 38, self.servo_support_active]:
                self.set_servo_position(angle)
                time.sleep(0.3)
        except Exception as e:
            self.node.get_logger().warn(f"⚠️ Failed to set servo position: {e}, continuing anyway")

        # === Move ZA group to Hold_Lens position using unified group delta ===
        # Get hold lens position from focus config
        hold_lens_pos = self.focus_config.get_hold_lens_position()
        
        # Calculate relative distance from current homed (Z=0, A=0) → target (Z, A)
        # If both are 59.0, just send 59mm distance
        distance = hold_lens_pos["Z"]  # Same as A; assumes homed position is 0

        steps = int(distance * 3200)
        direction = 0 if distance > 0 else 1

        self.node.get_logger().info(
            f"🎯 Moving ZA group to Hold_Lens: Z={hold_lens_pos['Z']} A={hold_lens_pos['A']} (M ZA {steps} {direction})"
        )
        self.send_motor_command(f"M ZA {steps} {direction}", scripted=False)
        time.sleep(11.0)  # Wait for ZA move to complete

        current["positions"]["ZA"]["Z"] = hold_lens_pos["Z"]
        current["positions"]["ZA"]["A"] = hold_lens_pos["A"]

        save_json(CURRENT_POS_PATH, current)



    def run_post_focus_sequence(self):
        self.node.get_logger().info("📦 Running post-focus sequence")
        self.send_annotation("phase", 0, "post_focus")

        positions = load_json(POSITIONS_PATH)
        current = load_json(CURRENT_POS_PATH)

        # Get post-focus parameters from config
        post_focus_params = self.focus_config.get_post_focus_params()
        lift_distance = post_focus_params['lift_distance']
        dot_laser_duration = post_focus_params['dot_laser_duration']
        
        # === Raise ZA by configured distance ===
        self.node.get_logger().info(f"⬆️ Lifting ZA by {lift_distance}mm")

        current_Z = current["positions"]["ZA"]["Z"]
        current_A = current["positions"]["ZA"]["A"]
        new_Z = current_Z + lift_distance
        new_A = current_A + lift_distance

        steps = int(lift_distance * 3200)
        direction = 1  # Always upward

        self.send_motor_command(f"M ZA {steps} {direction}", scripted=False)
        time.sleep(1.5)

        current["positions"]["ZA"]["Z"] = new_Z
        current["positions"]["ZA"]["A"] = new_A
        save_json(CURRENT_POS_PATH, current)

        # === Activate DOT laser ===
        self.node.get_logger().info(f"💡 Activating Dot Laser for {dot_laser_duration}s")
        self.send_motor_command("L 2 0", scripted=False)
        time.sleep(dot_laser_duration)
        self.send_motor_command("L 2 1", scripted=False)


        # === Return ZA to home ===
        self.node.get_logger().info("🏠 Homing ZA again")
        self.send_motor_command("H ZA", scripted=False)
        time.sleep(4.0)

        # Update after homing
        current["positions"]["ZA"]["Z"] = 0.0
        current["positions"]["ZA"]["A"] = 0.0
        current["homed"]["ZA"] = True
        save_json(CURRENT_POS_PATH, current)

        # === Servo back to HOME (safe) ===
        self.node.get_logger().info("🔄 Resetting servo to home (safe)")
        self.set_servo_position(self.servo_support_home)

    def set_servo_position(self, angle):
        self.send_motor_command(f"S {angle}", scripted=False)
        self.node.get_logger().info(f"🔄 Servo moved to {angle}°")

    def motor_ack_callback(self, msg):
        if msg.data.strip().lower() == "ack":
            self.ack_event.set()
    
    def reload_lens_config(self):
        """Reload lens configuration from file"""
        try:
            lens_profiles, default_settings, global_settings = load_lens_config()
            if lens_profiles:
                self.lens_focus_configs = lens_profiles
                self.global_settings = global_settings
                self.node.get_logger().info(f"✅ Reloaded lens configuration from {self.config_path}")
                # Log current lens config
                if self.lens_spec in self.lens_focus_configs:
                    roi_ratio = self.lens_focus_configs[self.lens_spec].get("roi_radius_ratio", "default")
                    self.node.get_logger().info(f"📐 Current lens {self.lens_spec} ROI ratio: {roi_ratio}")
                return True
            else:
                self.node.get_logger().warn("⚠️ Failed to reload lens configuration")
                return False
        except Exception as e:
            self.node.get_logger().error(f"❌ Error reloading lens config: {e}")
            return False

    def send_motor_command(self, command, scripted=True, wait_for_ack=True):
        self.ack_event.clear()
        pub = self.scripted_pub if scripted else self.direct_pub
        self.node.get_logger().info(f"🤖 Sending {'scripted' if scripted else 'direct'} command: {command}")
        pub.publish(String(data=command))
        if scripted and wait_for_ack:
            if not self.ack_event.wait(timeout=0.5):  # Reduced timeout from 3.0 to 0.5
                self.node.get_logger().warn(f"⏱️ Timeout waiting for ACK: {command} (motor bridge may be offline)")
            else:
                self.node.get_logger().info(f"✅ ACK received for: {command}")
                
    def send_annotation(self, annotation_type, position, label=None):
        if self.annotation_publisher:
            payload = {"type": annotation_type, "position": position}
            if label:
                payload["label"] = label
            self.annotation_publisher.publish(String(data=json.dumps(payload)))                

    def move_and_settle(self, steps, direction):
        self.send_motor_command(f"M D {steps} {direction}", scripted=True)

        

    def setup_camera(self):
        """Setup camera for focus operations - called lazily when needed"""
        # CRITICAL FIX: Always reset camera state to prevent lingering artifacts
        if self.cap:
            self.node.get_logger().info("🧹 Resetting camera state from previous session")
            self.cap.release()
            self.cap = None
            # Force garbage collection and brief delay for driver reset
            import gc
            gc.collect()
            time.sleep(1.0)  # Allow camera driver state to fully reset
            
        if self.cap and self.cap.isOpened():
            return True  # Camera already initialized
        
        # Set V4L2 data_rate to 0 for PGM camera compatibility
        # FSM cameras work with data_rate=0 (891/594 Mbps/lane)
        # PGM cameras default to data_rate=1 (445.5/297 Mbps/lane) which causes buffering issues
        import subprocess
        try:
            video_device = f"/dev/video{self.camera_id}"
            result = subprocess.run(
                ["v4l2-ctl", "--device", video_device, "--set-ctrl", "data_rate=0"],
                capture_output=True,
                text=True,
                check=False
            )
            if result.returncode == 0:
                self.logger.info(f"Set V4L2 data_rate=0 for {video_device} (PGM/FSM camera compatibility)")
            else:
                self.logger.warning(f"Could not set data_rate for {video_device}: {result.stderr}")
        except Exception as e:
            self.logger.warning(f"Error setting V4L2 controls: {e}")

        # Multiple pipeline options to try
        pipelines = [
            # 1. Simple pipeline (like visual_test_overlay.py uses)
            (
                f"nvarguscamerasrc sensor-position={self.camera_id} ! "
                f"nvvidconv ! video/x-raw, format=BGRx ! videoconvert ! "
                f"video/x-raw, format=BGR ! appsink drop=true"
            ),
            # 2. Pipeline with explicit caps
            (
                f"nvarguscamerasrc sensor-position={self.camera_id} ! "
                "video/x-raw(memory:NVMM), width=1280, height=720, format=NV12, framerate=30/1 ! "
                "nvvidconv ! video/x-raw, format=BGRx ! videoconvert ! "
                "video/x-raw, format=BGR ! appsink"
            ),
            # 3. Pipeline with sync=false to avoid blocking
            (
                f"nvarguscamerasrc sensor-position={self.camera_id} ! "
                f"nvvidconv ! video/x-raw, format=BGRx ! videoconvert ! "
                f"video/x-raw, format=BGR ! appsink drop=true sync=false"
            ),
            # 4. Direct V4L2 fallback (non-NVIDIA path)
            f"/dev/video{self.camera_id}"
        ]
        
        # Try each pipeline with retries
        for attempt in range(3):  # 3 attempts total
            if attempt > 0:
                self.node.get_logger().warning(f"⏳ Retry attempt {attempt + 1}/3, waiting 2 seconds...")
                time.sleep(2)
                
            for i, pipeline in enumerate(pipelines):
                try:
                    self.node.get_logger().info(f"📷 Attempt {attempt + 1}, trying pipeline {i + 1}/4: {pipeline[:80]}...")
                    
                    # Release any previous capture
                    if self.cap:
                        self.cap.release()
                        self.cap = None
                        time.sleep(0.5)  # Brief pause after release
                    
                    # Try to open the camera
                    if i < 3:  # GStreamer pipelines
                        self.cap = cv2.VideoCapture(pipeline, cv2.CAP_GSTREAMER)
                    else:  # V4L2 device
                        self.cap = cv2.VideoCapture(pipeline, cv2.CAP_V4L2)
                    
                    if self.cap.isOpened():
                        # Test reading a frame to ensure it's really working
                        ret, test_frame = self.cap.read()
                        if ret and test_frame is not None:
                            self.node.get_logger().info(f"✅ Camera opened successfully with pipeline {i + 1}, frame shape: {test_frame.shape}")
                            
                            # Start background threads for camera operations
                            if not hasattr(self, '_camera_threads_started'):
                                self.node.get_logger().info("🚀 Starting background camera threads...")
                                self.frame_grabber_thread = threading.Thread(target=self.background_frame_grabber, daemon=False)
                                self.renderer_thread = threading.Thread(target=self.render_live_feed, daemon=False)
                                self.frame_grabber_thread.start()
                                self.renderer_thread.start()
                                self._camera_threads_started = True
                                self.node.get_logger().info("✅ Background camera threads started")
                            
                            return True
                        else:
                            self.node.get_logger().warning(f"⚠️ Pipeline {i + 1} opened but couldn't read frame")
                            self.cap.release()
                            self.cap = None
                            
                except Exception as e:
                    self.node.get_logger().error(f"❌ Pipeline {i + 1} failed with exception: {e}")
                    if self.cap:
                        self.cap.release()
                        self.cap = None
        
        # All attempts failed
        self.node.get_logger().error("❌ Could not open camera after all attempts")
        self.node.get_logger().error(f"📋 OpenCV version: {cv2.__version__}")
        self.node.get_logger().error(f"📋 OpenCV GStreamer support: {'YES' if cv2.getBuildInformation().find('GStreamer:                   YES') > 0 else 'NO'}")
        return False
        
    def release_camera(self):
        """Release camera resources when focus operations complete"""
        self.node.get_logger().info("🧹 Starting camera resource cleanup")
        
        # Signal all threads to stop first
        self.shutdown_event.set()
        
        # Wait for threads to actually finish before proceeding
        if hasattr(self, 'frame_grabber_thread') and self.frame_grabber_thread.is_alive():
            self.node.get_logger().info("⏳ Waiting for frame grabber thread to finish...")
            self.frame_grabber_thread.join(timeout=3.0)
            if self.frame_grabber_thread.is_alive():
                self.node.get_logger().warning("⚠️ Frame grabber thread didn't finish in time - forcing cleanup")
                # CRITICAL FIX: Force thread cleanup to prevent resource leaks
                try:
                    import threading
                    if hasattr(threading, '_shutdown'):
                        self.node.get_logger().warning("🔧 Attempting forced thread cleanup")
                except Exception as e:
                    self.node.get_logger().error(f"Forced cleanup failed: {e}")
            else:
                self.node.get_logger().info("✅ Frame grabber thread finished")
        
        if hasattr(self, 'renderer_thread') and self.renderer_thread.is_alive():
            self.node.get_logger().info("⏳ Waiting for renderer thread to finish...")
            self.renderer_thread.join(timeout=3.0)
            if self.renderer_thread.is_alive():
                self.node.get_logger().warning("⚠️ Renderer thread didn't finish in time - forcing cleanup")
                # CRITICAL FIX: Force renderer thread cleanup
                try:
                    import threading
                    if hasattr(threading, '_shutdown'):
                        self.node.get_logger().warning("🔧 Attempting forced renderer cleanup")
                except Exception as e:
                    self.node.get_logger().error(f"Forced renderer cleanup failed: {e}")
            else:
                self.node.get_logger().info("✅ Renderer thread finished")
        
        # Now safely release camera with enhanced cleanup
        if self.cap and self.cap.isOpened():
            self.cap.release()
            self.cap = None
            self.node.get_logger().info("📷 Camera resources released")
            
        # CRITICAL FIX: Force complete camera state reset
        if self.cap:
            self.cap = None
            
        # Force garbage collection to ensure complete cleanup
        import gc
        gc.collect()
        
        # Additional delay to ensure camera driver state is fully reset
        time.sleep(0.5)
        self.node.get_logger().info("🧹 Camera driver state reset complete")
        
        # Reset thread tracking so camera can be reinitialized on next run
        if hasattr(self, '_camera_threads_started'):
            delattr(self, '_camera_threads_started')
            self.node.get_logger().info("🔄 Camera thread tracking reset for next run")
        
        # Clean up thread references
        if hasattr(self, 'frame_grabber_thread'):
            delattr(self, 'frame_grabber_thread')
        if hasattr(self, 'renderer_thread'):
            delattr(self, 'renderer_thread')
        
        # Reset shutdown event for next run
        self.shutdown_event.clear()
        self.node.get_logger().info("🔄 Shutdown event reset for next run")
        
        # Clear any other persistent state
        self.latest_frame = None
        self.frame_ready.clear()
        self.node.get_logger().info("🧹 Camera cleanup complete")

    def background_frame_grabber(self):
        try:
            self.node.get_logger().info("🧵 Frame grabber thread started")
            frame_count = 0
            while not self.shutdown_event.is_set() and self.cap and self.cap.isOpened():
                ret, frame = self.cap.read()
                if ret:
                    frame_count += 1
                    with self.frame_lock:
                        self.latest_frame = frame
                        self.frame_ready.set()
                    # Log every 10th frame to show activity
                    if frame_count % 10 == 0:
                        self.node.get_logger().info(f"📹 Captured frame #{frame_count}, shape: {frame.shape}")
                else:
                    self.node.get_logger().error("❌ Failed to read frame from camera")
                    break
            self.node.get_logger().info(f"🛑 Frame grabber thread stopping (captured {frame_count} frames)")
        except Exception as e:
            self.node.get_logger().error(f"❌ Frame grabber exception: {e}")
            import traceback
            self.node.get_logger().error(f"❌ Traceback: {traceback.format_exc()}")

    def render_live_feed(self):
        """Render the live camera feed using OpenCV (Xavier-compatible approach)"""
        try:
            import cv2
            import time
            
            self.node.get_logger().info("🖥️ Starting OpenCV live feed renderer (Xavier-compatible)")
            
            WINDOW_WIDTH, WINDOW_HEIGHT = 640, 360
            window_name = "Focus Live Feed"
            
            # Create OpenCV window
            cv2.namedWindow(window_name, cv2.WINDOW_NORMAL)
            cv2.resizeWindow(window_name, WINDOW_WIDTH, WINDOW_HEIGHT)
            
            # Check if window is actually displayable
            try:
                window_prop = cv2.getWindowProperty(window_name, cv2.WND_PROP_VISIBLE)
                self.node.get_logger().info(f"✅ OpenCV window created successfully, visible property: {window_prop}")
            except Exception as e:
                self.node.get_logger().warning(f"⚠️ Cannot check window property: {e}")

            frame_count = 0
            no_frame_count = 0
            
            # Wait for first frame to be available before starting render loop
            self.node.get_logger().info("🎬 Waiting for first frame...")
            while self.latest_frame is None and not self.shutdown_event.is_set():
                time.sleep(0.1)
                no_frame_count += 1
                if no_frame_count > 50:  # 5 seconds
                    self.node.get_logger().warning("⚠️ Still waiting for first frame...")
                    no_frame_count = 0
                elif no_frame_count % 10 == 0:  # Every second
                    self.node.get_logger().info(f"🎬 Waiting for first frame... ({no_frame_count/10:.1f}s), shutdown_event: {self.shutdown_event.is_set()}")
            
            if self.shutdown_event.is_set():
                self.node.get_logger().warning("📴 Renderer shutting down before first frame - shutdown_event was set!")
                return
            
            self.node.get_logger().info("🎬 First frame available, starting render loop")
            
            loop_count = 0
            while not self.shutdown_event.is_set():
                loop_count += 1
                frame_count += 1
                with self.frame_lock:
                    frame = self.latest_frame.copy() if self.latest_frame is not None else None
                
                # Debug log for early exit conditions
                if frame_count == 1:
                    self.node.get_logger().info(f"🎬 Starting OpenCV render loop - shutdown_event: {self.shutdown_event.is_set()}")
                
                # Log window status periodically
                if frame_count % 300 == 0:  # Every 10 seconds at 30fps
                    self.node.get_logger().info(f"Feed window active, frame #{frame_count}")
                elif frame_count == 1:
                    self.node.get_logger().info("🖼️ Rendering first frame")

                if frame is not None:
                    try:
                        # Keep BGR format for OpenCV display
                        resized = cv2.resize(frame, (WINDOW_WIDTH, WINDOW_HEIGHT))
                    except Exception as e:
                        self.node.get_logger().error(f"Frame processing error: {e}")
                        continue
                    
                    # Add ROI overlay
                    roi_ratio = self.lens_focus_configs.get(self.lens_spec, {}).get("roi_radius_ratio", 0.28)
                    roi_radius = int(min(WINDOW_WIDTH, WINDOW_HEIGHT) * roi_ratio)
                    roi_center_x, roi_center_y = WINDOW_WIDTH // 2, WINDOW_HEIGHT // 2
                    cv2.circle(resized, (roi_center_x, roi_center_y), roi_radius, (0, 255, 0), 2)
                    
                    # Add text overlay with focus score
                    overlay_text = f"Score: {self.current_score:.2f} | Phase: {self.current_phase}"
                    cv2.putText(resized, overlay_text, (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
                    
                    # Display frame using OpenCV
                    cv2.imshow(window_name, resized)
                    
                    # Check for ESC key only (window visibility check unreliable on Xavier)
                    key = cv2.waitKey(1) & 0xFF
                    if key == 27:
                        self.node.get_logger().info("🖼️ User pressed ESC - closing window")
                        break
                    
                    # Log every 100 frames to show progress
                    if frame_count % 100 == 0:
                        self.node.get_logger().info(f"🖼️ Display active - rendered {frame_count} frames")
                else:
                    cv2.waitKey(30)  # ~30 fps when no frame
            
            self.node.get_logger().info(f"🖥️ OpenCV live feed loop ended after {loop_count} iterations, shutdown_event: {self.shutdown_event.is_set()}")
            
        except Exception as e:
            self.node.get_logger().error(f"❌ Live feed renderer exception: {e}")
            import traceback
            self.node.get_logger().error(f"❌ Traceback: {traceback.format_exc()}")
        finally:
            # CRITICAL FIX: Cleanup OpenCV window
            try:
                if 'window_name' in locals():
                    cv2.destroyWindow(window_name)
                    self.node.get_logger().info("🖼️ OpenCV window destroyed")
                cv2.destroyAllWindows()
                self.node.get_logger().info("🧹 All OpenCV windows cleaned up")
            except Exception as cleanup_error:
                self.node.get_logger().error(f"OpenCV cleanup error: {cleanup_error}")
                
            self.node.get_logger().info("🖥️ Live feed renderer thread stopped")

    def measure_score(self):
        # Check if config needs reloading
        if self.global_settings.get("enable_hot_reload", False):
            try:
                stat = os.stat(self.config_path)
                if stat.st_mtime > self.config_last_modified:
                    self.reload_lens_config()
                    self.config_last_modified = stat.st_mtime
            except:
                pass
        
        self.frame_ready.wait(timeout=2)
        with self.frame_lock:
            frame = self.latest_frame.copy() if self.latest_frame is not None else None
        self.frame_ready.clear()

        if frame is None:
            self.node.get_logger().warn("⚠️ measure_score(): No frame available.")
            return None, None

        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

        # Get ROI radius from config (fallback to 0.28 if not set)
        roi_ratio = self.lens_focus_configs.get(self.lens_spec, {}).get("roi_radius_ratio", 0.28)

        # Create circular mask
        height, width = gray.shape
        center = (width // 2, height // 2)
        radius = int(min(width, height) * roi_ratio)
        mask = np.zeros_like(gray, dtype=np.uint8)
        cv2.circle(mask, center, radius, 255, -1)

        # Masked Laplacian variance
        masked_gray = cv2.bitwise_and(gray, gray, mask=mask)
        laplacian = cv2.Laplacian(masked_gray, cv2.CV_64F)
        score = float(np.var(laplacian))

        self.current_score = score
        return frame, score


    def run_focus_loop(self):
        # Initialize camera for focus operations
        self.node.get_logger().info("🔍 Attempting camera initialization...")
        camera_success = self.setup_camera()
        if not camera_success:
            self.node.get_logger().error("❌ Failed to initialize camera for focus operations")
            # TEMPORARY: Continue without camera for debugging
            self.node.get_logger().warning("⚠️ CONTINUING WITHOUT CAMERA FOR DEBUGGING")
            # return  # Commented out to bypass camera requirement
        else:
            self.node.get_logger().info("✅ Camera initialized successfully")
            
        from focus_control.tools.focus_shape_matcher import (
            match_focus_entry_zone,
            match_to_peak_profile,
            load_normalized_json,
        )
        import traceback
        import time
        import cv2
        import os
        from datetime import datetime
        import csv
        import json

        config = self.lens_focus_configs.get(self.lens_spec, self.lens_focus_configs["4mm"])
        micro_steps = config["micro_steps"]
        spike_threshold = config["spike_threshold"]
        entry_multiplier = config["entry_multiplier"]
        early_spike_delta = config["early_spike_delta"]
        settle_delay_micro = config["settle_delay_micro"]

        profiles, peak_scores = load_normalized_json()
        profile_key = f"{self.lens_spec}__{self.focus_distance}"
        expected_peak_score = peak_scores.get(profile_key, 100)
        min_required_score = expected_peak_score * 0.85

        # Check if recording is enabled
        recording_enabled = True
        recording_state_file = "/tmp/focus_recording_state.json"
        if os.path.exists(recording_state_file):
            try:
                with open(recording_state_file, 'r') as f:
                    state = json.load(f)
                    recording_enabled = state.get('recording_enabled', True)
            except:
                recording_enabled = True
        
        # Get serial number for this focus session (only if recording)
        if recording_enabled:
            serial_number = get_next_serial_number()
        else:
            serial_number = "NO_RECORD"
            self.node.get_logger().info("⏸️ Recording is paused - data will not be saved")
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        label = f"focus_{serial_number}_{self.lens_spec}_{self.focus_distance}mm_cam{self.camera_id}_{timestamp}"
        log_dir = "/home/ubuntu/focus_logs/process_logs"
        final_frame_dir = os.path.join(log_dir, "final_frame_images")
        
        if recording_enabled:
            os.makedirs(final_frame_dir, exist_ok=True)
            os.makedirs(log_dir, exist_ok=True)
        
        log_file = os.path.join(log_dir, f"{label}.csv") if recording_enabled else None
        
        # Store serial number for later use
        self.current_serial_number = serial_number

        if recording_enabled:
            self.node.get_logger().info(f"📜 Logging to: {log_file}")
            self.node.get_logger().info(f"📋 Serial Number: {serial_number}")
        else:
            self.node.get_logger().info("⏸️ Recording paused - no files will be saved")
        
        # Log serial number mapping for traceability (only if recording)
        if recording_enabled:
            serial_log_file = "/home/ubuntu/focus_logs/serial_number_log.csv"
            with open(serial_log_file, 'a', newline='') as f:
                writer = csv.writer(f)
                # Write header if file is new
                if os.path.getsize(serial_log_file) == 0:
                    writer.writerow(['serial_number', 'timestamp', 'lens_spec', 'focus_distance', 'camera_id', 'image_path', 'graph_path'])
                
                # Prepare paths for logging
                image_path = os.path.join(final_frame_dir, f"{label}.jpg")
                graph_path = f"/home/ubuntu/focus_logs/process_logs/graphs/{label}_graph_{serial_number}_{self.lens_spec}_{self.focus_distance}mm_cam{self.camera_id}_{timestamp}.png"
                
                writer.writerow([
                    serial_number,
                    datetime.now().isoformat(),
                    self.lens_spec,
                    self.focus_distance,
                    self.camera_id,
                    image_path,
                    graph_path
                ])
        self.send_annotation("phase", 0, "pre_focus")
        self.run_pre_focus_sequence()

        if not self.frame_ready.wait(timeout=5):
            self.node.get_logger().error("🚫 No frames received after 5s, exiting focus loop.")
            return
        self.node.get_logger().info("✅ First frame received.")

        entry_buffer = []
        best_score = 0.0
        best_position = 0
        direction = 1
        position = 0
        current_step = config["initial_step"]
        in_micro = False
        micro_index = 0
        frame = None
        last_score = 0.0
        previous_delta = 0.0

        # Open log file only if recording is enabled
        logfile = None
        writer = None
        if recording_enabled and log_file:
            logfile = open(log_file, 'w', newline='')
            writer = csv.writer(logfile)
            writer.writerow(['Position', 'Focus Score'])
        
        try:

                # Publish focus start event with serial number
                if self.focus_start_publisher:
                    start_data = json.dumps({
                        "status": "start",
                        "serial_number": self.current_serial_number,
                        "lens_spec": self.lens_spec,
                        "focus_distance": self.focus_distance,
                        "camera_id": self.camera_id
                    })
                    start_msg = String()
                    start_msg.data = start_data
                    self.focus_start_publisher.publish(start_msg)
                    self.node.get_logger().info(f"📢 Published focus_start message with {self.current_serial_number}")
                
                self.current_phase = "discovery"
                self.send_annotation("phase", position, self.current_phase)
                self.node.get_logger().info(f"🌀 Phase: {self.current_phase} | Step size: {current_step} | Start position: {position}")
                with self.plot_lock:
                    self.plotter.mark_phase(position, self.current_phase)

                while not self.shutdown_event.is_set():
                    frame, score = self.measure_score()
                    if frame is None or score is None:
                        continue

                    if writer:
                        writer.writerow([position, score])
                    self.score_publisher.publish(String(data=f"{position},{score:.2f}"))
                    self.node.get_logger().debug(f"📸 Frame OK | Pos: {position} | Score: {score:.2f}")

                    with self.plot_lock:
                        self.positions.append(position)
                        self.scores.append(score)
                        self.plotter.add_point(position, score)

                    entry_buffer.append(score)
                    if len(entry_buffer) > 5:
                        entry_buffer.pop(0)

                    if not in_micro and len(entry_buffer) >= 2:
                        delta = entry_buffer[-1] - entry_buffer[-2]
                        if delta >= spike_threshold or score > entry_multiplier * entry_buffer[0] or delta >= early_spike_delta:
                            self.node.get_logger().info("📈 Sharp rise — early spike detected, switching to micro")
                            in_micro = True
                            self.current_phase = "micro"
                            self.send_annotation("phase", position, self.current_phase)
                            current_step = micro_steps[micro_index]
                            self.node.get_logger().info(f"🌀 Phase: {self.current_phase} | Step size: {current_step} | Start position: {position}")
                            with self.plot_lock:
                                self.plotter.mark_phase(position, self.current_phase)
                            last_score = score
                            previous_delta = float('inf')
                            continue

                    if in_micro:
                        time.sleep(settle_delay_micro)
                        delta = score - last_score

                        if score > best_score:
                            best_score = score
                            best_position = position

                        if delta < previous_delta and micro_index + 1 < len(micro_steps):
                            micro_index += 1
                            current_step = micro_steps[micro_index]
                            self.node.get_logger().info(f"🔽 Slowing approach | Reduced step size: {current_step}")
                        previous_delta = delta
                        last_score = score

                        if delta < 0:
                            self.node.get_logger().info(f"🔒 Peak reached at {position} | Final best score: {best_score:.2f}")
                            if self.focus_done_publisher:
                                # Include serial number in completion message
                                completion_data = json.dumps({
                                    "status": "done",
                                    "serial_number": self.current_serial_number,
                                    "lens_spec": self.lens_spec,
                                    "focus_distance": self.focus_distance,
                                    "camera_id": self.camera_id,
                                    "best_score": best_score
                                })
                                self.focus_done_publisher.publish(String(data=completion_data))
                                self.node.get_logger().info(f"📢 Published focus_complete message with {self.current_serial_number}")
                            break

                    self.move_and_settle(current_step, direction)
                    position += current_step if direction == 1 else -current_step

                self.current_phase = "stable"
                self.send_annotation("phase", position, "stable")
                time.sleep(2.0)

                if frame is not None and recording_enabled:
                    final_path = os.path.join(final_frame_dir, f"{label}.jpg")
                    cv2.putText(frame, f"Score: {best_score:.2f}", (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 255, 0), 2)
                    cv2.imwrite(final_path, frame)
                    self.node.get_logger().info(f"🖼️ Final frame saved: {final_path}")

                # ✅ Post focus sequence runs here (only once!)
                self.node.get_logger().info("📦 Running post-focus sequence")
                self.run_post_focus_sequence()

        except Exception as e:
            self.node.get_logger().error(f"🚨 Error: {repr(e)}")
            self.node.get_logger().debug(traceback.format_exc())
        finally:
            if logfile:
                try:
                    logfile.flush()
                    os.fsync(logfile.fileno())
                    logfile.close()
                except Exception as e:
                    self.node.get_logger().warn(f"⚠️ Log flush failed: {e}")
            self.send_annotation("phase", 0, "post_focus")
            self.cleanup()



    def run_calibration(self):
        # Initialize camera for calibration operations
        if not self.setup_camera():
            self.node.get_logger().error("❌ Failed to initialize camera for calibration operations")
            return
            
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        label = f"calib_{self.lens_spec}_{self.focus_distance}m_cam{self.camera_id}_{timestamp}"

        base_dir = "/home/ubuntu/focus_logs/calibration_logs"
        csv_dir = os.path.join(base_dir, "CSVlogs")
        master_dir = os.path.join(base_dir, "master")
        os.makedirs(csv_dir, exist_ok=True)
        os.makedirs(master_dir, exist_ok=True)

        run_log_path = os.path.join(csv_dir, f"{label}.csv")
        master_log_path = os.path.join(master_dir, "master_calibrations.csv")

        self.node.get_logger().info(f"📋 Calibration log: {run_log_path}")
        self.set_servo_position(self.servo_support_active)

        calibration_step = 40
        calibration_delay = 0.03
        max_steps = 134000

        all_rows = []
        best_score = 0.0
        best_row = None
        frame_index = 0
        position = 0
        direction = 1

        try:
            with open(run_log_path, 'w', newline='') as logfile:
                writer = csv.writer(logfile)
                writer.writerow([
                    'LensSpec', 'DistanceM', 'Phase', 'Step', 'Score',
                    'Timestamp', 'FrameIndex', 'IsBest'
                ])

                self.node.get_logger().info(f"🔁 Starting calibration pass with step size {calibration_step}")
                with self.plot_lock:
                    self.plotter.mark_phase(position, "calibration")

                while not self.shutdown_event.is_set() and position < max_steps:
                    frame, score = self.measure_score()
                    if frame is None:
                        continue

                    frame_index += 1
                    is_best = ""
                    if score > best_score:
                        best_score = score
                        is_best = "TRUE"
                        best_row = [
                            self.lens_spec, self.focus_distance, "calibration",
                            position, score, timestamp, frame_index, is_best
                        ]

                    row = [
                        self.lens_spec, self.focus_distance, "calibration",
                        position, score, timestamp, frame_index, is_best
                    ]
                    writer.writerow(row)
                    all_rows.append(row)

                    self.score_publisher.publish(String(data=f"{position},{score:.2f}"))
                    with self.plot_lock:
                        self.positions.append(position)
                        self.scores.append(score)
                        self.plotter.add_point(position, score)

                    self.move_and_settle(calibration_step, direction)
                    position += calibration_step
                    time.sleep(calibration_delay)

                    if position % (20 * calibration_step) == 0:
                        self.send_motor_command("S 38", scripted=False)
                        time.sleep(0.03)
                        self.send_motor_command("S 34", scripted=False)
                        with self.plot_lock:
                            self.plotter.mark_servo_bump(position)

                logfile.flush()
                os.fsync(logfile.fileno())

        except Exception as e:
            self.node.get_logger().error(f"🚨 Calibration error: {e}")

        finally:
            time.sleep(0.2)
            try:
                if all_rows:
                    master_exists = os.path.exists(master_log_path)
                    with open(master_log_path, 'a', newline='') as masterfile:
                        master_writer = csv.writer(masterfile)
                        if not master_exists:
                            master_writer.writerow([
                                'LensSpec', 'DistanceM', 'Phase', 'Step', 'Score',
                                'Timestamp', 'FrameIndex', 'IsBest'
                            ])
                        master_writer.writerows(all_rows)

                    self.node.get_logger().info(f"📦 Appended {len(all_rows)} rows to master CSV")
                    if best_row:
                        self.node.get_logger().info(
                            f"🏆 Best Score: {best_row[4]:.2f} at Step {best_row[3]} (Frame #{best_row[6]})"
                        )
                else:
                    self.node.get_logger().warn("⚠️ No calibration rows captured, master CSV not updated.")
            except Exception as e:
                self.node.get_logger().error(f"💥 Failed to update master CSV: {e}")

            self.current_phase = "calibration"
            self.cleanup()


    def emergency_stop_cleanup(self):
        """Emergency cleanup when user stops focus mid-process"""
        self.node.get_logger().info("🛑 Emergency stop - performing safe cleanup sequence")
        
        try:
            # Safe sequence: Lift ZA, then home servo, then home ZA
            self.node.get_logger().info("📍 Step 1: Lifting ZA by 5mm for safety")
            self.send_motor_command("M ZA 16000 0", scripted=False, wait_for_ack=False)  # Direct command, no ACK wait
            time.sleep(3.0)  # Generous time for lift to complete
            
            self.node.get_logger().info("📍 Step 2: Moving servo to home position")
            self.send_motor_command(f"S {self.servo_support_home}", scripted=False, wait_for_ack=False)
            time.sleep(2.0)  # Generous time for servo to reach home
            
            self.node.get_logger().info("📍 Step 3: Homing ZA axis")
            self.send_motor_command("H ZA", scripted=False, wait_for_ack=False)  # Direct home command
            time.sleep(5.0)  # Extra time for homing to complete (ZA takes longest)
            
            self.node.get_logger().info("📍 Step 4: Clearing motor queue")
            # Clear any remaining commands in the queue
            from rclpy.qos import QoSProfile
            queue_pub = self.node.create_publisher(String, 'clear_scripted_queue', QoSProfile(depth=1))
            queue_pub.publish(String(data="clear"))
            time.sleep(0.5)  # Allow queue clear to process
            
        except Exception as e:
            self.node.get_logger().error(f"❌ Error during emergency cleanup: {e}")
        finally:
            pass  # No need to signal shutdown here as release_camera() handles it
            
        # Clean up camera resources (this will signal shutdown to threads)
        self.release_camera()
        self.node.get_logger().info("✅ Emergency cleanup complete")

    def cleanup(self):
        """Normal cleanup after successful focus completion"""
        self.node.get_logger().info("🧹 Performing normal cleanup sequence")
        
        try:
            # Normal sequence: servo home
            self.set_servo_position(self.servo_support_home)
        except Exception as e:
            self.node.get_logger().error(f"❌ Error during normal cleanup: {e}")
            
        # Clean up camera resources (this will also signal shutdown to threads)
        self.release_camera()
        self.node.get_logger().info("✅ Normal cleanup complete")
        
    def safe_b_axis_move(self, camera_id, timeout=30.0):
        """Move B axis to camera position and wait for completion"""
        self.node.get_logger().info(f"🎯 Moving B axis to camera {camera_id} position")
        
        # Get camera position from focus config
        target_mm = self.focus_config.get_camera_position(camera_id)
        if target_mm is None:
            raise ValueError(f"No configured position for Camera{camera_id}")
        
        # Load current position
        current = load_json(CURRENT_POS_PATH)
        current_mm = current["positions"]["B"]["B"]
        
        self.node.get_logger().info(f"📐 Target B position: {target_mm}mm (current: {current_mm}mm)")
        
        # Calculate relative movement needed
        delta_mm = target_mm - current_mm
        if abs(delta_mm) < 0.01:  # Already at position
            self.node.get_logger().info(f"✅ B axis already at camera {camera_id} position")
            return True
            
        # Convert to steps and direction
        steps = int(abs(delta_mm) * 3200)  # 3200 steps/mm for B axis
        direction = 0 if delta_mm > 0 else 1
        
        self.node.get_logger().info(f"🔄 Moving B axis: {delta_mm:.2f}mm = {steps} steps, direction {direction}")
        
        # Send move command with timeout protection
        try:
            self.node.get_logger().info(f"🤖 Sending command: M B {steps} {direction}")
            
            # Use direct command instead of scripted to avoid ACK issues
            self.send_motor_command(f"M B {steps} {direction}", scripted=False, wait_for_ack=False)
            
            # Give it time to move based on distance (but don't wait for ACK)
            move_time = max(2.0, abs(delta_mm) / 20.0)  # Estimate time based on distance
            self.node.get_logger().info(f"⏱️ Allowing {move_time:.1f}s for B-axis movement")
            time.sleep(move_time)
            
            self.node.get_logger().info("✅ B-axis movement time elapsed")
            
        except Exception as e:
            self.node.get_logger().error(f"❌ B-axis move failed: {e}")
            # Continue anyway - don't let B-axis failure block focus
            self.node.get_logger().warning("⚠️ Continuing focus despite B-axis issue")
        
        # Update current position (optimistically)
        current["positions"]["B"]["B"] = target_mm
        save_json(CURRENT_POS_PATH, current)
        
        self.node.get_logger().info(f"✅ B axis positioning attempt complete for camera {camera_id}")
        return True


