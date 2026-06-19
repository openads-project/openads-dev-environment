#!/usr/bin/env python3

# Copyright Institute for Automotive Engineering (ika), RWTH Aachen University
# SPDX-License-Identifier: Apache-2.0

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node, SetParameter


def generate_launch_description():
    """Generate the launch description for the sample_pkg_no_params node."""

    remappable_topics = [
        DeclareLaunchArgument("input_topic", default_value="~/input"),
        DeclareLaunchArgument("output_topic", default_value="~/output"),
        DeclareLaunchArgument("service_topic", default_value="~/service"),
    ]

    args = [
        DeclareLaunchArgument("name", default_value="sample_pkg_no_params", description="node name"),
        DeclareLaunchArgument("namespace", default_value="", description="node namespace"),
        DeclareLaunchArgument(
            "log_level", default_value="info", description="ROS logging level (debug, info, warn, error, fatal)"
        ),
        DeclareLaunchArgument("use_sim_time", default_value="false", description="use simulation clock"),
        *remappable_topics,
    ]

    nodes = [
        Node(
            package="sample_pkg_no_params",
            executable="sample_pkg_no_params",
            namespace=LaunchConfiguration("namespace"),
            name=LaunchConfiguration("name"),
            arguments=["--ros-args", "--log-level", LaunchConfiguration("log_level")],
            remappings=[(la.default_value[0].text, LaunchConfiguration(la.name)) for la in remappable_topics],
            output="screen",
            emulate_tty=True,
        )
    ]

    return LaunchDescription(
        [
            *args,
            SetParameter("use_sim_time", LaunchConfiguration("use_sim_time")),
            *nodes,
        ]
    )