#!/usr/bin/env python3
"""
Quick utility to update focus system positions.
Use this to easily adjust Hold_Lens position and camera positions.
"""

import sys
import os
sys.path.append('/space/ros2_ws/src/focus_control/focus_control')
from focus_positions_config import FocusPositionsConfig

def main():
    config = FocusPositionsConfig()
    
    if len(sys.argv) == 1:
        # No arguments - show current config
        config.print_config()
        print("\n" + "="*50)
        print("Usage:")
        print("  Show positions:     python3 update_focus_positions.py")
        print("  Update hold lens:   python3 update_focus_positions.py hold_lens <ZA_position>")
        print("  Update camera:      python3 update_focus_positions.py camera <num> <B>")
        print("  Update servo:       python3 update_focus_positions.py servo <home|active> <angle>")
        print("  Update post-focus:  python3 update_focus_positions.py post <lift|laser> <value>")
        print("\nExamples:")
        print("  python3 update_focus_positions.py hold_lens 60")
        print("  python3 update_focus_positions.py camera 0 -5.0")
        print("  python3 update_focus_positions.py servo active 35")
        print("  python3 update_focus_positions.py post lift 6.0")
        return
    
    command = sys.argv[1].lower()
    
    try:
        if command == "hold_lens":
            if len(sys.argv) != 3:
                print("Error: hold_lens requires ZA position value")
                print("Usage: python3 update_focus_positions.py hold_lens <ZA_position>")
                return
            za_pos = float(sys.argv[2])
            # For ZA axis, both Z and A move together to the same position
            config.update_hold_lens_position(za_pos, za_pos)
            print(f"✅ Updated Hold_Lens position to ZA={za_pos}mm (both Z and A axes)")
            
        elif command == "camera":
            if len(sys.argv) != 4:
                print("Error: camera requires camera number (0-5) and B position")
                print("Usage: python3 update_focus_positions.py camera <num> <B>")
                return
            camera_num = int(sys.argv[2])
            if camera_num < 0 or camera_num > 5:
                print("Error: Camera number must be 0-5")
                return
            b_pos = float(sys.argv[3])
            config.update_camera_position(camera_num, b_pos)
            print(f"✅ Updated Camera{camera_num} B-axis position to {b_pos}mm")
            
        elif command == "servo":
            if len(sys.argv) != 4:
                print("Error: servo requires type (home/active) and angle")
                print("Usage: python3 update_focus_positions.py servo <home|active> <angle>")
                return
            servo_type = sys.argv[2].lower()
            angle = int(sys.argv[3])
            if servo_type == "home":
                config.update_servo_positions(home=angle)
                print(f"✅ Updated servo home position to {angle}°")
            elif servo_type == "active":
                config.update_servo_positions(active=angle)
                print(f"✅ Updated servo active position to {angle}°")
            else:
                print("Error: Servo type must be 'home' or 'active'")
                return
                
        elif command == "post":
            if len(sys.argv) != 4:
                print("Error: post requires parameter (lift/laser) and value")
                print("Usage: python3 update_focus_positions.py post <lift|laser> <value>")
                return
            param = sys.argv[2].lower()
            value = float(sys.argv[3])
            if param == "lift":
                config.update_post_focus_params(lift_distance=value)
                print(f"✅ Updated post-focus lift distance to {value}mm")
            elif param == "laser":
                config.update_post_focus_params(dot_laser_duration=value)
                print(f"✅ Updated dot laser duration to {value}s")
            else:
                print("Error: Post-focus parameter must be 'lift' or 'laser'")
                return
                
        else:
            print(f"Error: Unknown command '{command}'")
            print("Valid commands: hold_lens, camera, servo, post")
            return
            
        # Show updated config
        print("\nUpdated configuration:")
        config.print_config()
        
    except ValueError as e:
        print(f"Error: Invalid value - {e}")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    main()