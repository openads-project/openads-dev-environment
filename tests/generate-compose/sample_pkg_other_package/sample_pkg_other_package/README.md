# `sample_pkg_other_package`

Sample package

| Topic | Type | Description |
| --- | --- | --- |
| `~/input` | `example_msgs/msg/Input` | Input topic |

#### Published Topics

| Topic | Type | Description |
| --- | --- | --- |
| `~/output` | `example_msgs/msg/Output` | Output topic |

## Launch Files

### [`sample_pkg_other_package.launch.py`](launch/sample_pkg_other_package.launch.py)

| Argument | Default | Description |
| --- | --- | --- |
| `input_topic` | `"~/input"` | TODO |
| `output_topic` | `"~/output"` | TODO |
| `service_topic` | `"~/service"` | TODO |
| `name` | `"sample_pkg_other_package"` | node name |
| `namespace` | `""` | node namespace |
| `params` | `os.path.join(get_package_share_directory("sample_pkg_other_package"), "config", "params.yml")` | path to parameter file |
| `log_level` | `"info"` | ROS logging level (debug, info, warn, error, fatal) |
| `use_sim_time` | `"false"` | use simulation clock |
