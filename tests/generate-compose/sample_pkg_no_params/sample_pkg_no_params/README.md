# `sample_pkg_no_params`

Sample package

| Topic | Type | Description |
| --- | --- | --- |
| `~/input` | `example_msgs/msg/Input` | Input topic |

#### Published Topics

| Topic | Type | Description |
| --- | --- | --- |
| `~/output` | `example_msgs/msg/Output` | Output topic |

## Launch Files

### [`no_params.launch.py`](launch/no_params.launch.py)

| Argument | Default | Description |
| --- | --- | --- |
| `input_topic` | `"~/input"` | TODO |
| `output_topic` | `"~/output"` | TODO |
| `service_topic` | `"~/service"` | TODO |
| `name` | `"sample_pkg_no_params"` | node name |
| `namespace` | `""` | node namespace |
| `log_level` | `"info"` | ROS logging level (debug, info, warn, error, fatal) |
| `use_sim_time` | `"false"` | use simulation clock |
