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
        service_clients=[],
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


def test_render_ordinary_topic_as_unquoted_mermaid_label() -> None:
    """Preserve existing Mermaid output for labels without special syntax."""
    generator = load_generator()

    assert generator.render_mermaid_edge_label("~/point_cloud") == "~/point_cloud"


def test_extract_service_clients_from_cpp_source() -> None:
    """Extract direct ROS service clients created by a node."""
    generator = load_generator()
    source = """
      left_turn_indicator_service_client_ =
          this->create_client<std_srvs::srv::SetBool>("~/enable_left_turn_indicator");
      right_turn_indicator_service_client_ =
          this->create_client<std_srvs::srv::SetBool>("~/enable_right_turn_indicator");
      hazard_lights_service_client_ =
          this->create_client<std_srvs::srv::SetBool>("~/enable_hazard_lights");
    """

    aliases = {}

    assert generator.extract_service_clients(source, aliases) == [
        generator.ServiceInterface(
            name="~/enable_left_turn_indicator",
            srv_type="std_srvs/srv/SetBool",
        ),
        generator.ServiceInterface(
            name="~/enable_right_turn_indicator",
            srv_type="std_srvs/srv/SetBool",
        ),
        generator.ServiceInterface(
            name="~/enable_hazard_lights",
            srv_type="std_srvs/srv/SetBool",
        ),
    ]


def test_extract_service_clients_ignores_action_clients() -> None:
    """Do not classify rclcpp_action clients as ROS service clients."""
    generator = load_generator()
    source = """
      action_client_ = rclcpp_action::create_client<PlanRoute>(
          this, "/planning/lanelet2_route_planning/plan_route");
      enable_client_ =
          this->create_client<std_srvs::srv::SetBool>("~/enable");
    """

    aliases = {}

    assert generator.extract_service_clients(source, aliases) == [
        generator.ServiceInterface(name="~/enable", srv_type="std_srvs/srv/SetBool")
    ]


def test_extract_service_clients_from_python_source() -> None:
    """Extract ROS service clients from a Python node."""
    generator = load_generator()
    source = """
from std_srvs.srv import SetBool


class ExampleNode(Node):
    def __init__(self):
        super().__init__("example")
        self.client = self.create_client(SetBool, "~/enable")
"""

    interfaces = generator.extract_python_node_interfaces(source, "fallback")

    assert interfaces is not None
    assert interfaces.service_clients == [
        generator.ServiceInterface(name="~/enable", srv_type="std_srvs/srv/SetBool")
    ]


def test_service_clients_reach_node_template_context() -> None:
    """Propagate service clients from node interfaces into the template context."""
    generator = load_generator()
    node = generator.NodeInterfaces(
        node_name="simple_planner_node",
        service_clients=[
            generator.ServiceInterface(
                name="~/enable_left_turn_indicator",
                srv_type="std_srvs/srv/SetBool",
            )
        ],
    )

    context = generator.build_node_context(node, {}, {}, {})

    assert context.service_clients == [
        generator.InterfaceTableRow(
            name="~/enable_left_turn_indicator",
            interface_type="std_srvs/srv/SetBool",
            description="TODO",
        )
    ]


def test_service_client_only_node_gets_diagram_and_edge() -> None:
    """A node with only service clients must still get a Mermaid diagram and edge."""
    generator = load_generator()
    node = generator.NodeTemplateContext(
        node_name="simple_planner_node",
        manual_text="",
        subscribers=[],
        publishers=[],
        service_servers=[],
        service_clients=[
            generator.InterfaceTableRow(
                name="~/enable_left_turn_indicator",
                interface_type="std_srvs/srv/SetBool",
                description="TODO",
            )
        ],
        action_servers=[],
        action_clients=[],
        parameters=[],
    )
    context = generator.PackageTemplateContext(
        package_name="simple_planner",
        package_description="Simple planner",
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

    assert "```mermaid" in rendered
    assert "NODE o--o|~/enable_left_turn_indicator| SC0:::hidden" in rendered
    assert "#### Service Clients" in rendered
