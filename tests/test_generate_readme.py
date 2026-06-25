#!/usr/bin/env python3

# Copyright Institute for Automotive Engineering (ika), RWTH Aachen University
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import importlib.util
from dataclasses import asdict
from pathlib import Path

DEV_ENV_ROOT = Path(__file__).resolve().parents[1]
GENERATOR_PATH = DEV_ENV_ROOT / "scripts" / "generate_readme.py"


def load_generator():
    """Load the README generator as a module."""
    spec = importlib.util.spec_from_file_location("generate_readme", GENERATOR_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_extract_point_cloud_subscriber_filter_with_variable_topic() -> None:
    """Extract the topic from SubscriberFilter::subscribe(node, topic, ...)."""
    generator = load_generator()
    source = """
      const std::string configured = input_topics_[i];
      const std::string resolved =
          this->get_node_topics_interface()->resolve_topic_name(configured);
      auto subscriber =
          std::make_shared<point_cloud_transport::SubscriberFilter>();
      subscriber->subscribe(
          this->shared_from_this(), resolved, hint,
          rmw_qos_profile_default, subscription_options);
    """

    aliases = {}
    string_symbols = generator.extract_cpp_string_symbols(source)
    variable_types = generator.extract_cpp_variable_types(source)

    assert generator.extract_subscribers(
        source, aliases, string_symbols, variable_types
    ) == [
        generator.TopicInterface(
            name="input_topics_[i]",
            msg_type="sensor_msgs/msg/PointCloud2",
        )
    ]


def test_extract_transport_subscriber_with_topic_first() -> None:
    """Keep supporting transport subscribe calls whose first argument is the topic."""
    generator = load_generator()
    source = """
      image_transport::ImageTransport transport(node);
      transport.subscribe("~/image", 1, callback);
    """

    aliases = {}
    string_symbols = generator.extract_cpp_string_symbols(source)
    variable_types = generator.extract_cpp_variable_types(source)

    assert generator.extract_subscribers(
        source, aliases, string_symbols, variable_types
    ) == [
        generator.TopicInterface(
            name="~/image",
            msg_type="sensor_msgs/msg/Image",
        )
    ]


def test_describe_indexed_topic_from_parameter() -> None:
    """Use an indexed topic parameter's description for the generated topic row."""
    generator = load_generator()

    descriptions = generator.add_dynamic_topic_parameter_descriptions(
        {},
        [
            generator.TopicInterface(
                name="input_topics_[i]",
                msg_type="sensor_msgs/msg/PointCloud2",
            )
        ],
        [
            generator.Parameter(
                name="input_topics",
                ros_type="string[]",
                default="[]",
                description="Point-cloud topics to fuse",
            )
        ],
    )

    assert descriptions == {"input_topics_[i]": "Point-cloud topics to fuse"}


def test_render_indexed_topic_as_quoted_mermaid_label() -> None:
    """Quote generated Mermaid labels so indexed topic expressions remain valid."""
    generator = load_generator()
    node = generator.NodeTemplateContext(
        node_name="point_cloud_fusion",
        manual_text="",
        subscribers=[
            generator.InterfaceTableRow(
                name="input_topics_[i]",
                interface_type="sensor_msgs/msg/PointCloud2",
                description="Point-cloud topics to fuse",
            )
        ],
        publishers=[],
        service_servers=[],
        action_servers=[],
        action_clients=[],
        parameters=[],
    )
    context = generator.PackageTemplateContext(
        package_name="point_cloud_fusion",
        package_description="Point-cloud fusion",
        sections=[
            generator.PackageSection(
                title="Nodes",
                kind="nodes",
                nodes=[node],
            )
        ],
    )

    rendered = (
        generator.build_template_environment()
        .get_template("package_readme.md.j2")
        .render(**asdict(context))
    )

    assert '-->|"input_topics_[i]"| NODE' in rendered
