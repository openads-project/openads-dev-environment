#!/usr/bin/env python3

# Copyright Institute for Automotive Engineering (ika), RWTH Aachen University
# SPDX-License-Identifier: Apache-2.0

from launch.actions import IncludeLaunchDescription


def generate_launch_description():
    return [
        IncludeLaunchDescription("first_node.launch.py"),
        IncludeLaunchDescription("second_node_launch.py"),
    ]
