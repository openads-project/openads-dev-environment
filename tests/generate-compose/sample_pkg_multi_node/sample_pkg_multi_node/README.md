# `sample_pkg_multi_node`

Sample package

#### Subscribed Topics

| Topic | Type | Description |
| --- | --- | --- |
| `~/input` | `example_msgs/msg/Input` | Input topic |
| `~/input_other` | `example_msgs/msg/Input` | Other input topic |

#### Published Topics

| Topic | Type | Description |
| --- | --- | --- |
| `~/output` | `example_msgs/msg/Output` | Output topic |
| `~/output_other` | `example_msgs/msg/Output` | Other output topic |

## Launch Files

### [`multi_node.launch.py`](launch/multi_node.launch.py)

| Argument | Default | Description |
| --- | --- | --- |
| `input_topic` | `"~/input"` | TODO |
| `output_topic` | `"~/output"` | TODO |
| `service_topic` | `"~/service"` | TODO |
| `input_topic_other` | `"~/input_other"` | TODO |
| `output_topic_other` | `"~/output_other"` | TODO |
| `service_topic_other` | `"~/service_other"` | TODO |
| `name` | `"sample_pkg_multi_node"` | node name |
| `namespace` | `""` | node namespace |
| `params` | `os.path.join(get_package_share_directory("sample_pkg_multi_node"), "config", "params.yml")` | path to parameter file |
| `params_other` | `os.path.join(get_package_share_directory("other_pkg"), "config", "params_other.yml")` | path to other parameter file |
| `log_level` | `"info"` | ROS logging level (debug, info, warn, error, fatal) |
| `use_sim_time` | `"false"` | use simulation clock |
