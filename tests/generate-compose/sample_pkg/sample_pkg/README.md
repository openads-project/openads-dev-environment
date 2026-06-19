# `sample_pkg`

Sample package

#### Subscribed Topics

| Topic | Type | Description |
| --- | --- | --- |
| `~/input` | `example_msgs/msg/Input` | Input topic |

#### Published Topics

| Topic | Type | Description |
| --- | --- | --- |
| `~/output` | `example_msgs/msg/Output` | Output topic |

## Launch Files

### [`other.launch.py`](launch/other.launch.py)

| Argument | Default | Description |
| --- | --- | --- |
| `input_topic` | `"~/input"` | TODO |
| `output_topic` | `"~/output"` | TODO |
| `service_topic` | `"~/service"` | TODO |
| `name` | `"other_pkg"` | node name |
| `namespace` | `""` | node namespace |
| `params` | `os.path.join(get_package_share_directory("other_pkg"), "config", "params.yml")` | path to parameter file |
| `log_level` | `"info"` | ROS logging level (debug, info, warn, error, fatal) |
| `use_sim_time` | `"false"` | use simulation clock |

### [`sample_pkg.launch.py`](launch/sample_pkg.launch.py)

| Argument | Default | Description |
| --- | --- | --- |
| `input_topic` | `"~/input"` | TODO |
| `output_topic` | `"~/output"` | TODO |
| `service_topic` | `"~/service"` | TODO |
| `name` | `"sample_pkg"` | node name |
| `namespace` | `""` | node namespace |
| `params` | `os.path.join(get_package_share_directory("sample_pkg"), "config", "params.yml")` | path to parameter file |
| `log_level` | `"info"` | ROS logging level (debug, info, warn, error, fatal) |
| `use_sim_time` | `"false"` | use simulation clock |
