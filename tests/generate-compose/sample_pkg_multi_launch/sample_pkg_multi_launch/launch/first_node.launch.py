#!/usr/bin/env python3

# Copyright Institute for Automotive Engineering (ika), RWTH Aachen University
# SPDX-License-Identifier: Apache-2.0

import os

from ament_index_python import get_package_share_directory
from launch.actions import DeclareLaunchArgument
from launch_ros.actions import Node


def generate_launch_description():
    remappable_topics = [
        DeclareLaunchArgument("input_topic", default_value="~/input"),
        DeclareLaunchArgument("output_topic", default_value="~/output"),
    ]
    args = [
        DeclareLaunchArgument("name", default_value="first_node"),
        DeclareLaunchArgument("namespace", default_value=""),
        DeclareLaunchArgument(
            "params",
            default_value=os.path.join(
                get_package_share_directory("sample_pkg_multi_launch"), "config", "params.first_node.yml"
            ),
        ),
        DeclareLaunchArgument("log_level", default_value="info"),
        DeclareLaunchArgument("use_sim_time", default_value="false"),
        *remappable_topics,
    ]
    node = Node(package="sample_pkg_multi_launch", executable="first_node")
    return [*args, node]
