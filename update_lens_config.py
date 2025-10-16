#!/usr/bin/env python3
"""
Quick utility to update lens ROI configuration without rebuilding ROS2
Usage: python3 update_lens_config.py [lens] [roi_ratio]
Example: python3 update_lens_config.py 2.8mm 0.50
"""

import sys
import json
import os

CONFIG_PATH = "/space/ros2_ws/lens_config.json"

def load_config():
    with open(CONFIG_PATH, 'r') as f:
        return json.load(f)

def save_config(config):
    with open(CONFIG_PATH, 'w') as f:
        json.dump(config, f, indent=2)

def list_lenses(config):
    print("\nCurrent lens configurations:")
    print("-" * 50)
    for lens, settings in config['lens_profiles'].items():
        roi = settings.get('roi_radius_ratio', 'not set')
        print(f"{lens:8s} - ROI ratio: {roi}")
    print("-" * 50)

def update_roi(lens_spec, new_roi_ratio):
    config = load_config()
    
    if lens_spec not in config['lens_profiles']:
        print(f"Error: Lens '{lens_spec}' not found in configuration")
        list_lenses(config)
        return False
    
    old_roi = config['lens_profiles'][lens_spec].get('roi_radius_ratio', 'not set')
    config['lens_profiles'][lens_spec]['roi_radius_ratio'] = new_roi_ratio
    
    save_config(config)
    print(f"✅ Updated {lens_spec} ROI ratio: {old_roi} → {new_roi_ratio}")
    return True

def main():
    if len(sys.argv) == 1:
        # No arguments - list current config
        config = load_config()
        list_lenses(config)
        print("\nUsage: python3 update_lens_config.py [lens] [roi_ratio]")
        print("Example: python3 update_lens_config.py 2.8mm 0.50")
        
    elif len(sys.argv) == 3:
        # Update specific lens
        lens_spec = sys.argv[1]
        try:
            roi_ratio = float(sys.argv[2])
            if 0 < roi_ratio <= 1:
                update_roi(lens_spec, roi_ratio)
            else:
                print(f"Error: ROI ratio must be between 0 and 1 (got {roi_ratio})")
        except ValueError:
            print(f"Error: Invalid ROI ratio '{sys.argv[2]}' - must be a decimal number")
    else:
        print("Usage: python3 update_lens_config.py [lens] [roi_ratio]")
        print("Or run without arguments to see current configuration")

if __name__ == "__main__":
    main()