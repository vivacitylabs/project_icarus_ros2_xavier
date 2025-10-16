#!/bin/bash
#
# Project Icarus - Start Focus Control Node
#
# Quick start script for the ROS2 focus control service.
# Sources the ROS2 workspace and launches the focus_script node.
#
# Usage:
#   ./start_focus_node.sh
#
# The focus control node provides services for automated camera focusing
# and communicates with the Jetson Nano/ESP32 motor control chain.
#

export DISPLAY=:0
export PYTHONPATH=""
cd /space/ros2_ws
source /opt/ros/foxy/setup.bash
source /space/ros2_ws/install/setup.bash
exec /usr/bin/python3 /space/ros2_ws/install/focus_control/lib/focus_control/focus_script
