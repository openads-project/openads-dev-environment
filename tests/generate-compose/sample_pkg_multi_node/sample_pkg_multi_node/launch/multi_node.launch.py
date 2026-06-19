#!/usr/bin/env python3

# Copyright Institute for Automotive Engineering (ika), RWTH Aachen University
# SPDX-License-Identifier: Apache-2.0

import os

from ament_index_python import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node, SetParameter


def generate_launch_description():
    """Generate the launch description for the sample_pkg_multi_node and other_pkg nodes."""

    remappable_topics = [
        DeclareLaunchArgument("input_topic", default_value="~/input"),
        DeclareLaunchArgument("output_topic", default_value="~/output"),
        DeclareLaunchArgument("service_topic", default_value="~/service"),
        DeclareLaunchArgument("input_topic_other", default_value="~/input_other"),
        DeclareLaunchArgument("output_topic_other", default_value="~/output_other"),
        DeclareLaunchArgument("service_topic_other", default_value="~/service_other"),
    ]

    args = [
        DeclareLaunchArgument("name", default_value="sample_pkg_multi_node", description="node name"),
        DeclareLaunchArgument("namespace", default_value="", description="node namespace"),
        DeclareLaunchArgument(
            "params",
            default_value=os.path.join(get_package_share_directory("sample_pkg_multi_node"), "config", "params.yml"),
            description="path to parameter file",
        ),
        DeclareLaunchArgument(
            "params_other",
            default_value=os.path.join(get_package_share_directory("other_pkg"), "config", "params_other.yml"),
            description="path to other parameter file",
        ),
        DeclareLaunchArgument(
            "log_level", default_value="info", description="ROS logging level (debug, info, warn, error, fatal)"
        ),
        DeclareLaunchArgument("use_sim_time", default_value="false", description="use simulation clock"),
        *remappable_topics,
    ]

    nodes = [
        Node(
            package="sample_pkg_multi_node",
            executable="sample_pkg_multi_node",
            namespace=LaunchConfiguration("namespace"),
            name=LaunchConfiguration("name"),
            parameters=[LaunchConfiguration("params")],
            arguments=["--ros-args", "--log-level", LaunchConfiguration("log_level")],
            remappings=[(la.default_value[0].text, LaunchConfiguration(la.name)) for la in remappable_topics],
            output="screen",
            emulate_tty=True,
        ),
        Node(
            package="other_pkg",
            executable="other_pkg",
            namespace=LaunchConfiguration("namespace"),
            name=[LaunchConfiguration("name"), "_other"],
            parameters=[LaunchConfiguration("params_other")],
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
