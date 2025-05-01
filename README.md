# project_icarus_ros2_xavier

This repository contains the ROS 2 workspace for the **Jetson Xavier** node 

used in [Project Icarus](https://github.com/vivacitylabs/project_icarus), a distributed focus automation system for Framos M12 camera modules.

---

## Overview

The Xavier is the master node responsible for executing the full autofocus process, rendering live video and focus scores, and coordinating motion across the system.

It communicates with the Jetson Nano over ROS 2 and integrates with the Flask web UI.

---

## Features

- Full focus pipeline with coarse, fine, and micro scoring phases
- Real-time video preview rendereding
- Laplacian-based focus scoring 
- Score history graph with Matplotlib (live + saved)
- Focus loop phase tracking and annotation
- Calibration mode with CSV logging and profile normalization
- ROS 2 integration with slave node on Nano
---

## Dependencies

- ROS 2 Foxy (or compatible)
- Python 3.8+
- OpenCV 
- ModernGL
- Matplotlib
- NumPy, SciPy

---

## Build Instructions

```bash
cd ~/space/ros2_ws
source /opt/ros/foxy/setup.bash
colcon build
source install/setup.bash

Running

ros2 run focus_control focus_script

This will:

    Start the focus control logic

    Connect to the Nano via ROS 2 topics

    Initialize the live renderer and score tracking

Related Repositories

    project_icarus: Flask UI and main system controller

    project_icarus_ros2_nano: ROS 2 node running on the Jetson Nano (handles serial comms)
