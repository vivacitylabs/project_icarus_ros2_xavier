# focus_session.py
# Location: ~/space/ros2_ws/src/focus_control/focus_control/focus_session.py

import cv2
import csv
import time
import os
POSITIONS_PATH = "/home/ubuntu/space/projects/project_icarus/positions.json"
CURRENT_POS_PATH = "/home/ubuntu/space/projects/project_icarus/current_position.json"

import glfw
import json
import numpy as np
import threading
from datetime import datetime
from std_msgs.msg import String
import moderngl

def load_json(path):
    with open(path, 'r') as f:
        return json.load(f)

def save_json(path, data):
    with open(path, 'w') as f:
        json.dump(data, f, indent=2)
        
class FocusSession:
    def __init__(self, node, score_publisher, plotter, camera_id, lens_spec, focus_distance, annotation_publisher=None, focus_done_publisher=None):
        self.node = node
        self.cap = None
        self.latest_frame = None
        self.shutdown_event = threading.Event()
        self.frame_lock = threading.Lock()
        self.frame_ready = threading.Event()

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

        self.plot_lock = threading.Lock()

        self.servo_support_active = 34
        self.servo_support_home = 120
        
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

        # === Home ZA first ===
        self.node.get_logger().info("🏠 Homing ZA")
        self.send_motor_command("H ZA", scripted=False)
        time.sleep(2.0)
        current["positions"]["ZA"]["Z"] = 0.0
        current["positions"]["ZA"]["A"] = 0.0

        # === Servo to HOME (safe down = 120°) ===
        self.node.get_logger().info("↩️ Setting servo to home (safe)")
        self.set_servo_position(self.servo_support_home)
        time.sleep(2.0)

        # === Move B to camera module ===
        cam_key = f"Camera{self.camera_id}"
        if cam_key in positions["saved_positions"]["B"]:
            cam_pos = positions["saved_positions"]["B"][cam_key]["B"]
            delta = cam_pos - current["positions"]["B"]["B"]
            if abs(delta) > 0.01:
                steps = int(abs(delta) * 3200)
                direction = 0 if delta > 0 else 1
                self.node.get_logger().info(f"🎯 Moving B to {cam_key}: Δ={delta:.2f}")
                self.send_motor_command(f"M B {steps} {direction}", scripted=False)
                time.sleep(8.0)  # wait for B move to finish
                current["positions"]["B"]["B"] = cam_pos
        else:
            self.node.get_logger().warn(f"⚠️ No saved B position for {cam_key}")

        # === Move ZA group to Hold_Lens position using unified group delta ===
        if "Hold_Lens" in positions["saved_positions"]["ZA"]:
            target = positions["saved_positions"]["ZA"]["Hold_Lens"]

            # Calculate relative distance from current homed (Z=0, A=0) → target (Z, A)
            # If both are 59.0, just send 59mm distance
            distance = target["Z"]  # Same as A; assumes homed position is 0

            steps = int(distance * 3200)
            direction = 0 if distance > 0 else 1

            self.node.get_logger().info(
                f"🎯 Moving ZA group to Hold_Lens: Z={target['Z']} A={target['A']} (M ZA {steps} {direction})"
            )
            self.send_motor_command(f"M ZA {steps} {direction}", scripted=False)
            time.sleep(11.0)  # Wait for ZA move to complete

            current["positions"]["ZA"]["Z"] = target["Z"]
            current["positions"]["ZA"]["A"] = target["A"]
        else:
            self.node.get_logger().warn("⚠️ No Hold_Lens position in ZA saved_positions")

        # === Servo to ACTIVE (raise to hold lens) ===
        self.node.get_logger().info("🤖 Raising servo to hold lens")
        for angle in [40, 38, self.servo_support_active]:
            self.set_servo_position(angle)
            time.sleep(0.3)

        save_json(CURRENT_POS_PATH, current)



    def run_post_focus_sequence(self):
        self.node.get_logger().info("📦 Running post-focus sequence")
        self.send_annotation("phase", 0, "post_focus")

        positions = load_json(POSITIONS_PATH)
        current = load_json(CURRENT_POS_PATH)

        # === Raise ZA by 5mm ===
        lift_distance = 5.0
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
        self.node.get_logger().info("💡 Activating Dot Laser for 8s")
        self.send_motor_command("L 2 0", scripted=False)
        time.sleep(8.0)
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

    def send_motor_command(self, command, scripted=True, wait_for_ack=True):
        self.ack_event.clear()
        pub = self.scripted_pub if scripted else self.direct_pub
        pub.publish(String(data=command))
        if scripted and wait_for_ack:
            if not self.ack_event.wait(timeout=3.0):
                self.node.get_logger().warn(f"⏱️ Timeout waiting for ACK: {command}")
                
    def send_annotation(self, annotation_type, position, label=None):
        if self.annotation_publisher:
            payload = {"type": annotation_type, "position": position}
            if label:
                payload["label"] = label
            self.annotation_publisher.publish(String(data=json.dumps(payload)))                

    def move_and_settle(self, steps, direction):
        self.send_motor_command(f"M D {steps} {direction}", scripted=True)

        

    def setup_camera(self):
        pipeline = (
            f"nvarguscamerasrc sensor-position={self.camera_id} ! "
            "video/x-raw(memory:NVMM), width=1280, height=720, format=NV12, framerate=30/1 ! "
            "nvvidconv ! video/x-raw, format=BGRx ! videoconvert ! "
            "video/x-raw, format=BGR ! appsink"
        )
        self.cap = cv2.VideoCapture(pipeline, cv2.CAP_GSTREAMER)
        if not self.cap.isOpened():
            self.node.get_logger().error("❌ Could not open camera.")
            return False
        return True

    def background_frame_grabber(self):
        while not self.shutdown_event.is_set() and self.cap and self.cap.isOpened():
            ret, frame = self.cap.read()
            if ret:
                with self.frame_lock:
                    self.latest_frame = frame
                    self.frame_ready.set()

    def render_live_feed(self):
        WINDOW_WIDTH, WINDOW_HEIGHT = 640, 360
        if not glfw.init():
            self.node.get_logger().error("❌ GLFW init failed")
            return

        glfw.window_hint(glfw.VISIBLE, glfw.TRUE)
        glfw.window_hint(glfw.RESIZABLE, glfw.FALSE)
        glfw.window_hint(glfw.CONTEXT_CREATION_API, glfw.EGL_CONTEXT_API)

        window = glfw.create_window(WINDOW_WIDTH, WINDOW_HEIGHT, "Focus Live Feed", None, None)
        if not window:
            self.node.get_logger().error("❌ Failed to create window")
            glfw.terminate()
            return

        glfw.make_context_current(window)
        ctx = moderngl.create_context()
        ctx.viewport = (0, 0, WINDOW_WIDTH, WINDOW_HEIGHT)

        program = ctx.program(
            vertex_shader="""
                #version 330
                in vec2 in_vert;
                in vec2 in_tex;
                out vec2 v_tex;
                void main() {
                    gl_Position = vec4(in_vert, 0.0, 1.0);
                    v_tex = in_tex;
                }
            """,
            fragment_shader="""
                #version 330
                uniform sampler2D Texture;
                in vec2 v_tex;
                out vec4 f_color;
                void main() {
                    f_color = texture(Texture, v_tex);
                }
            """
        )

        vertices = np.array([
            -1.0, -1.0, 0.0, 0.0,
             1.0, -1.0, 1.0, 0.0,
            -1.0,  1.0, 0.0, 1.0,
             1.0,  1.0, 1.0, 1.0,
        ], dtype='f4')

        vbo = ctx.buffer(vertices.tobytes())
        vao = ctx.simple_vertex_array(program, vbo, 'in_vert', 'in_tex')
        texture = ctx.texture((WINDOW_WIDTH, WINDOW_HEIGHT), 3, dtype='f1')
        texture.use()

        while not glfw.window_should_close(window) and not self.shutdown_event.is_set():
            with self.frame_lock:
                frame = self.latest_frame.copy() if self.latest_frame is not None else None

            if frame is not None:
                rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                resized = cv2.resize(rgb, (WINDOW_WIDTH, WINDOW_HEIGHT))
                
                roi_ratio = self.lens_focus_configs.get(self.lens_spec, {}).get("roi_radius_ratio", 0.28)
                h, w = resized.shape[:2]
                center = (w // 2, h // 2)
                radius = int(min(w, h) * roi_ratio)
                cv2.circle(resized, center, radius, (0, 255, 0), 2)  # green circle
                
                flipped = cv2.flip(resized, 0)
                texture.write(flipped.tobytes())

                overlay_text = f"Score: {self.current_score:.2f} | Phase: {self.current_phase}"
                glfw.set_window_title(window, f"Live Feed - {overlay_text}")

                ctx.clear(0.1, 0.1, 0.1)
                vao.render(moderngl.TRIANGLE_STRIP)
                glfw.swap_buffers(window)

            glfw.poll_events()
            time.sleep(1 / 30.0)

        glfw.destroy_window(window)
        glfw.terminate()
        self.node.get_logger().info("🛑 Live feed closed")

    def measure_score(self):
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

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        label = f"focus_{self.lens_spec}_{self.focus_distance}mm_cam{self.camera_id}_{timestamp}"
        log_dir = "/home/ubuntu/focus_logs/process_logs"
        final_frame_dir = os.path.join(log_dir, "final_frame_images")
        os.makedirs(final_frame_dir, exist_ok=True)
        os.makedirs(log_dir, exist_ok=True)
        log_file = os.path.join(log_dir, f"{label}.csv")

        self.node.get_logger().info(f"📜 Logging to: {log_file}")
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

        try:
            with open(log_file, 'w', newline='') as logfile:
                writer = csv.writer(logfile)
                writer.writerow(['Position', 'Focus Score'])

                self.current_phase = "discovery"
                self.send_annotation("phase", position, self.current_phase)
                self.node.get_logger().info(f"🌀 Phase: {self.current_phase} | Step size: {current_step} | Start position: {position}")
                with self.plot_lock:
                    self.plotter.mark_phase(position, self.current_phase)

                while not self.shutdown_event.is_set():
                    frame, score = self.measure_score()
                    if frame is None or score is None:
                        continue

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
                                self.focus_done_publisher.publish(String(data="done"))
                                self.node.get_logger().info("📢 Published focus_complete message")
                            break

                    self.move_and_settle(current_step, direction)
                    position += current_step if direction == 1 else -current_step

                self.current_phase = "stable"
                self.send_annotation("phase", position, "stable")
                time.sleep(2.0)

                if frame is not None:
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
            try:
                logfile.flush()
                os.fsync(logfile.fileno())
            except Exception as e:
                self.node.get_logger().warn(f"⚠️ Log flush failed: {e}")
            self.send_annotation("phase", 0, "post_focus")
            self.cleanup()



    def run_calibration(self):
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


    def cleanup(self):
        self.set_servo_position(self.servo_support_home)
        self.shutdown_event.set()
        if self.cap:
            self.cap.release()
        cv2.destroyAllWindows()
        self.node.get_logger().info("🧹 Camera released, OpenCV shutdown")


