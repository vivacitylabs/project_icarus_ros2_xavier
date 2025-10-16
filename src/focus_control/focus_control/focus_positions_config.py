#!/usr/bin/env python3
"""
Centralized configuration for focus system positions.
This module provides easy access and modification of critical positions
used during the focusing process.
"""

import json
import os
from typing import Dict, Any, Optional

# Default positions that can be overridden
DEFAULT_FOCUS_POSITIONS = {
    "hold_lens": {
        "Z": 59.0,
        "A": 59.0,
        "description": "ZA position for holding the lens during focus"
    },
    "camera_positions": {
        "Camera0": {"B": -4.5, "description": "Position 1 (top)"},
        "Camera1": {"B": -48.2, "description": "Position 2"},
        "Camera2": {"B": -92.9, "description": "Position 3"},
        "Camera3": {"B": -136.0, "description": "Position 4"},
        "Camera4": {"B": -179.9, "description": "Position 5"},
        "Camera5": {"B": -223.6, "description": "Position 6 (bottom)"}
    },
    "servo_positions": {
        "home": 120,
        "active": 34,
        "description": "Servo angles for lens holder"
    },
    "post_focus": {
        "lift_distance": 5.0,
        "dot_laser_duration": 8.0,
        "description": "Post-focus sequence parameters"
    }
}

class FocusPositionsConfig:
    """Manager for focus system positions configuration."""
    
    def __init__(self, config_path: Optional[str] = None):
        """Initialize with optional custom config path."""
        if config_path is None:
            # Use the main positions.json file
            config_path = "/home/ubuntu/space/projects/project_icarus/positions.json"
        self.config_path = config_path
        # Secondary config for servo and post-focus params
        self.secondary_config_path = os.path.join(
            os.path.dirname(__file__), 
            "focus_params.json"
        )
        self.positions = self._load_config()
    
    def _load_config(self) -> Dict[str, Any]:
        """Load configuration from main positions.json and extract focus-related positions."""
        focus_positions = DEFAULT_FOCUS_POSITIONS.copy()
        
        if os.path.exists(self.config_path):
            try:
                with open(self.config_path, 'r') as f:
                    main_positions = json.load(f)
                    
                # Extract focus-related positions from main file
                if "saved_positions" in main_positions:
                    # Hold Lens position
                    if "ZA" in main_positions["saved_positions"] and "Hold_Lens" in main_positions["saved_positions"]["ZA"]:
                        hold_lens = main_positions["saved_positions"]["ZA"]["Hold_Lens"]
                        focus_positions["hold_lens"]["Z"] = hold_lens.get("Z", 59.0)
                        focus_positions["hold_lens"]["A"] = hold_lens.get("A", 59.0)
                    
                    # Camera positions
                    if "B" in main_positions["saved_positions"]:
                        for i in range(6):
                            cam_key = f"Camera{i}"
                            if cam_key in main_positions["saved_positions"]["B"]:
                                focus_positions["camera_positions"][cam_key]["B"] = main_positions["saved_positions"]["B"][cam_key]["B"]
                
            except Exception as e:
                print(f"Error loading config: {e}, using defaults")
        
        # Load servo and post-focus params from secondary config
        if os.path.exists(self.secondary_config_path):
            try:
                with open(self.secondary_config_path, 'r') as f:
                    secondary = json.load(f)
                    if "servo_positions" in secondary:
                        focus_positions["servo_positions"].update(secondary["servo_positions"])
                    if "post_focus" in secondary:
                        focus_positions["post_focus"].update(secondary["post_focus"])
            except Exception:
                pass  # Use defaults if secondary config doesn't exist
        
        return focus_positions
    
    def _merge_configs(self, default: Dict, loaded: Dict) -> Dict:
        """Merge loaded config with defaults, preserving loaded values."""
        result = default.copy()
        for key, value in loaded.items():
            if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                result[key] = self._merge_configs(result[key], value)
            else:
                result[key] = value
        return result
    
    def _save_to_main_positions(self) -> None:
        """Save focus positions back to the main positions.json file."""
        try:
            # Load the current main positions file
            with open(self.config_path, 'r') as f:
                main_positions = json.load(f)
            
            # Ensure structure exists
            if "saved_positions" not in main_positions:
                main_positions["saved_positions"] = {}
            
            # Update Hold Lens position
            if "ZA" not in main_positions["saved_positions"]:
                main_positions["saved_positions"]["ZA"] = {}
            main_positions["saved_positions"]["ZA"]["Hold_Lens"] = {
                "Z": self.positions["hold_lens"]["Z"],
                "A": self.positions["hold_lens"]["A"]
            }
            
            # Update Camera positions
            if "B" not in main_positions["saved_positions"]:
                main_positions["saved_positions"]["B"] = {}
            for cam_key, cam_data in self.positions["camera_positions"].items():
                if isinstance(cam_data, dict) and "B" in cam_data:
                    main_positions["saved_positions"]["B"][cam_key] = {"B": cam_data["B"]}
            
            # Save back to file
            with open(self.config_path, 'w') as f:
                json.dump(main_positions, f, indent=2)
                
        except Exception as e:
            print(f"Error saving to main positions.json: {e}")
    
    def _save_secondary_config(self) -> None:
        """Save servo and post-focus params to secondary config file."""
        try:
            secondary = {
                "servo_positions": self.positions["servo_positions"],
                "post_focus": self.positions["post_focus"]
            }
            with open(self.secondary_config_path, 'w') as f:
                json.dump(secondary, f, indent=2)
        except Exception as e:
            print(f"Error saving secondary config: {e}")
    
    def get_hold_lens_position(self) -> Dict[str, float]:
        """Get the ZA position for holding the lens."""
        return {
            "Z": self.positions["hold_lens"]["Z"],
            "A": self.positions["hold_lens"]["A"]
        }
    
    def get_camera_position(self, camera_num: int) -> Optional[float]:
        """Get B-axis position for a specific camera (0-5)."""
        camera_key = f"Camera{camera_num}"
        camera_data = self.positions["camera_positions"].get(camera_key)
        return camera_data["B"] if camera_data else None
    
    def get_servo_positions(self) -> Dict[str, int]:
        """Get servo positions for home and active states."""
        return {
            "home": self.positions["servo_positions"]["home"],
            "active": self.positions["servo_positions"]["active"]
        }
    
    def get_post_focus_params(self) -> Dict[str, float]:
        """Get post-focus sequence parameters."""
        return {
            "lift_distance": self.positions["post_focus"]["lift_distance"],
            "dot_laser_duration": self.positions["post_focus"]["dot_laser_duration"]
        }
    
    def update_hold_lens_position(self, z: float, a: float) -> None:
        """Update the hold lens position and save to file."""
        self.positions["hold_lens"]["Z"] = z
        self.positions["hold_lens"]["A"] = a
        self._save_to_main_positions()
    
    def update_camera_position(self, camera_num: int, b_position: float) -> None:
        """Update a specific camera's B-axis position."""
        camera_key = f"Camera{camera_num}"
        if camera_key in self.positions["camera_positions"]:
            self.positions["camera_positions"][camera_key]["B"] = b_position
            self._save_to_main_positions()
    
    def update_servo_positions(self, home: Optional[int] = None, active: Optional[int] = None) -> None:
        """Update servo positions."""
        if home is not None:
            self.positions["servo_positions"]["home"] = home
        if active is not None:
            self.positions["servo_positions"]["active"] = active
        self._save_secondary_config()
    
    def update_post_focus_params(self, lift_distance: Optional[float] = None, 
                                dot_laser_duration: Optional[float] = None) -> None:
        """Update post-focus parameters."""
        if lift_distance is not None:
            self.positions["post_focus"]["lift_distance"] = lift_distance
        if dot_laser_duration is not None:
            self.positions["post_focus"]["dot_laser_duration"] = dot_laser_duration
        self._save_secondary_config()
    
    def reload(self) -> None:
        """Reload configuration from file."""
        self.positions = self._load_config()
    
    def get_all_positions(self) -> Dict[str, Any]:
        """Get all configured positions."""
        return self.positions.copy()
    
    def print_config(self) -> None:
        """Print current configuration in a readable format."""
        print("\n=== Focus Positions Configuration ===")
        print(f"\nHold Lens Position (ZA):")
        print(f"  Z: {self.positions['hold_lens']['Z']}mm")
        print(f"  A: {self.positions['hold_lens']['A']}mm")
        
        print(f"\nCamera Positions (B-axis):")
        for cam, data in self.positions['camera_positions'].items():
            if isinstance(data, dict) and 'B' in data:
                print(f"  {cam}: {data['B']}mm - {data.get('description', '')}")
        
        print(f"\nServo Positions:")
        print(f"  Home: {self.positions['servo_positions']['home']}°")
        print(f"  Active: {self.positions['servo_positions']['active']}°")
        
        print(f"\nPost-Focus Parameters:")
        print(f"  Lift Distance: {self.positions['post_focus']['lift_distance']}mm")
        print(f"  Dot Laser Duration: {self.positions['post_focus']['dot_laser_duration']}s")


# Convenience functions for quick updates
def update_hold_lens_position(z: float, a: float) -> None:
    """Quick function to update hold lens position."""
    config = FocusPositionsConfig()
    config.update_hold_lens_position(z, a)
    print(f"Updated Hold Lens position to Z={z}, A={a}")

def update_camera_position(camera_num: int, b_position: float) -> None:
    """Quick function to update a camera position."""
    config = FocusPositionsConfig()
    config.update_camera_position(camera_num, b_position)
    print(f"Updated Camera{camera_num} B-axis position to {b_position}")

def show_focus_positions() -> None:
    """Display all current focus positions."""
    config = FocusPositionsConfig()
    config.print_config()


if __name__ == "__main__":
    # Example usage and testing
    print("Focus Positions Configuration Tool")
    print("-" * 40)
    
    config = FocusPositionsConfig()
    config.print_config()
    
    print("\n\nExample commands:")
    print("  Update hold lens: update_hold_lens_position(60.0, 60.0)")
    print("  Update camera: update_camera_position(0, -5.0)")
    print("  Show all: show_focus_positions()")