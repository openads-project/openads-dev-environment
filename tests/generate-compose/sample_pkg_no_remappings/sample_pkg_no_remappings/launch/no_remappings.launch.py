#!/usr/bin/env python3

# Copyright Institute for Automotive Engineering (ika), RWTH Aachen University
# SPDX-License-Identifier: Apache-2.0

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node, SetParameter


def generate_launch_description():
    """Generate a launch description without remappable topics."""
    remappable_topics = []

    args = [
        DeclareLaunchArgument("namespace", default_value="", description="node namespace"),
        DeclareLaunchArgument(
            "log_level", default_value="info", description="ROS logging level (debug, info, warn, error, fatal)"
        ),
        DeclareLaunchArgument("use_sim_time", default_value="false", description="use simulation clock"),
        *remappable_topics,
    ]

    nodes = [
        Node(
            package="sample_pkg_no_remappings",
            executable="sample_pkg_no_remappings",
            namespace=LaunchConfiguration("namespace"),
            name="side_a",
            arguments=["--ros-args", "--log-level", LaunchConfiguration("log_level")],
            output="screen",
            emulate_tty=True,
        ),
        Node(
            package="sample_pkg_no_remappings",
            executable="sample_pkg_no_remappings",
            namespace=LaunchConfiguration("namespace"),
            name="side_b",
            arguments=["--ros-args", "--log-level", LaunchConfiguration("log_level")],
            output="screen",
            emulate_tty=True,
        ),
    ]

    return LaunchDescription(
        [
            *args,
            SetParameter("use_sim_time", LaunchConfiguration("use_sim_time")),
            *nodes,
        ]
    )
