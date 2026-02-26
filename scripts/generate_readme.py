#!/usr/bin/env python3
"""
Auto-generates ROS2 interface documentation (topics, actions, parameters)
by parsing C++ source files in a ROS2 repository and inserting the result
into the "## Auto-generated Package Documentation" section of README.md.
If that section does not exist it is appended at the bottom.

Usage:
    python3 scripts/generate_readme.py [REPO_ROOT]

REPO_ROOT defaults to the script's parent directory.
The README updated is REPO_ROOT/README.md.
"""

import difflib
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional
from xml.etree import ElementTree


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class TopicInterface:
    name: str
    msg_type: str


@dataclass
class ActionInterface:
    name: str
    action_type: str


@dataclass
class Parameter:
    name: str
    ros_type: str
    default: str
    description: str


@dataclass
class NodeInterfaces:
    node_name: str
    subscribers: list = field(default_factory=list)
    publishers: list = field(default_factory=list)
    action_servers: list = field(default_factory=list)
    action_clients: list = field(default_factory=list)
    parameters: list = field(default_factory=list)


# ---------------------------------------------------------------------------
# Type helpers
# ---------------------------------------------------------------------------

def cpp_ros_type(cpp_type: str, type_aliases: dict) -> str:
    """Resolve type aliases and convert C++ ROS type to ROS notation (:: -> /)."""
    t = cpp_type.strip()
    t = type_aliases.get(t, t)
    return t.replace('::', '/').strip()


def cpp_param_type(cpp_type: str) -> str:
    """Map C++ type to ROS parameter type name."""
    t = cpp_type.strip()
    if t in ('double', 'float'):
        return 'float'
    if t == 'int':
        return 'int'
    if t == 'bool':
        return 'bool'
    if t == 'std::string':
        return 'string'
    if 'vector' in t:
        return 'string[]'
    return t


def format_default(default_str: Optional[str], cpp_type: str) -> str:
    """Format a C++ default value for Markdown display."""
    if default_str is None:
        return '[]' if 'vector' in cpp_type else ''
    val = default_str.strip()
    if val.startswith('"') and val.endswith('"'):
        val = val[1:-1]
    return val


# ---------------------------------------------------------------------------
# Discovery
# ---------------------------------------------------------------------------

def find_packages(repo_root: Path) -> list:
    """Return [(package_name, package_dir)] for all ROS packages found."""
    packages = []
    for pkg_xml in sorted(repo_root.rglob('package.xml')):
        try:
            root = ElementTree.parse(pkg_xml).getroot()
            name_el = root.find('name')
            if name_el is not None and name_el.text:
                packages.append((name_el.text.strip(), pkg_xml.parent))
        except ElementTree.ParseError:
            pass
    return packages


def find_node_sources(package_dir: Path) -> list:
    """Return .cpp files that define a ROS node (contain ': Node("..." )')."""
    node_pattern = re.compile(r':\s*Node\s*\(')
    return [
        cpp for cpp in sorted(package_dir.rglob('*.cpp'))
        if node_pattern.search(cpp.read_text(errors='replace'))
    ]


def find_headers(package_dir: Path) -> list:
    """Return all header files (.hpp, .h) in the package."""
    return [
        p for ext in ('*.hpp', '*.h')
        for p in sorted(package_dir.rglob(ext))
    ]


def find_launch_files(package_dir: Path) -> list:
    """Return launch files (.py, .xml, .yaml) found in any launch/ subdirectory."""
    launch_dir = package_dir / 'launch'
    if not launch_dir.is_dir():
        return []
    return [
        p for ext in ('*.py', '*.xml', '*.yaml', '*.yml')
        for p in sorted(launch_dir.rglob(ext))
    ]


# ---------------------------------------------------------------------------
# Extraction from source/header text
# ---------------------------------------------------------------------------

def extract_node_name(source: str) -> Optional[str]:
    m = re.search(r':\s*Node\s*\(\s*"([^"]+)"', source)
    return m.group(1) if m else None


def extract_subscribers(source: str, aliases: dict) -> list:
    return [
        TopicInterface(name=m.group(2), msg_type=cpp_ros_type(m.group(1), aliases))
        for m in re.finditer(r'create_subscription\s*<([^>]+)>\s*\(\s*"([^"]+)"', source)
    ]


def extract_publishers(source: str, aliases: dict) -> list:
    return [
        TopicInterface(name=m.group(2), msg_type=cpp_ros_type(m.group(1), aliases))
        for m in re.finditer(r'create_publisher\s*<([^>]+)>\s*\(\s*"([^"]+)"', source)
    ]


def extract_action_servers(source: str, aliases: dict) -> list:
    return [
        ActionInterface(name=m.group(2), action_type=cpp_ros_type(m.group(1), aliases))
        for m in re.finditer(
            r'rclcpp_action::create_server\s*<([^>]+)>\s*\(\s*this\s*,\s*"([^"]+)"', source)
    ]


def extract_action_clients(source: str, aliases: dict) -> list:
    return [
        ActionInterface(name=m.group(2), action_type=cpp_ros_type(m.group(1), aliases))
        for m in re.finditer(
            r'rclcpp_action::create_client\s*<([^>]+)>\s*\(\s*this\s*,\s*"([^"]+)"', source)
    ]


def extract_raw_parameters(source: str) -> list:
    """Return [(param_name, member_var_name, description)] from declareAndLoadParameter calls."""
    return [
        (m.group(1), m.group(2), m.group(3))
        for m in re.finditer(
            r'declareAndLoadParameter\s*\(\s*"([^"]+)"\s*,\s*(\w+)\s*,\s*"([^"]+)"', source)
    ]


def extract_python_launch_arguments(source: str) -> list:
    """Return [(name, default, description)] from DeclareLaunchArgument calls in a .py file."""
    results = []
    for m in re.finditer(r'DeclareLaunchArgument\s*\(', source):
        # Walk forward to find the matching closing parenthesis.
        start, depth, i = m.end(), 1, m.end()
        while i < len(source) and depth > 0:
            if source[i] == '(':
                depth += 1
            elif source[i] == ')':
                depth -= 1
            i += 1
        call_body = source[start:i - 1]

        name_m = re.match(r'\s*"([^"]+)"', call_body)
        if not name_m:
            continue
        name = name_m.group(1)

        dv_m = re.search(r'default_value\s*=\s*"([^"]*)"', call_body)
        if dv_m:
            default = dv_m.group(1)
        else:
            dv_expr = re.search(
                r'default_value\s*=\s*(.+?)(?=,\s*\w+\s*=|\s*$)', call_body, re.DOTALL)
            default = dv_expr.group(1).strip() if dv_expr else ''

        desc_m = re.search(r'description\s*=\s*"([^"]*)"', call_body)
        description = desc_m.group(1) if desc_m else ''

        results.append((name, default, description))
    return results


def extract_xml_launch_arguments(source: str) -> list:
    """Return [(name, default, description)] from <arg> elements in a .xml launch file."""
    results = []
    for m in re.finditer(r'<arg\b([^/]*)/>', source, re.DOTALL):
        attrs = m.group(1)
        name_m = re.search(r'\bname\s*=\s*"([^"]+)"', attrs)
        if not name_m:
            continue
        default_m = re.search(r'\bdefault\s*=\s*"([^"]*)"', attrs)
        desc_m = re.search(r'\bdescription\s*=\s*"([^"]*)"', attrs)
        results.append((
            name_m.group(1),
            default_m.group(1) if default_m else '',
            desc_m.group(1) if desc_m else '',
        ))
    return results


def extract_launch_arguments(path: Path) -> list:
    """Dispatch to the correct extractor based on file extension."""
    source = path.read_text(errors='replace')
    if path.suffix == '.xml':
        return extract_xml_launch_arguments(source)
    return extract_python_launch_arguments(source)


def build_member_var_map(headers: list) -> dict:
    """Return {var_name: (cpp_type, default_str)} from member variable declarations."""
    pattern = re.compile(
        r'\b(double|float|int|bool|std::string|std::vector\s*<[^>]+>)\s+(\w+_)\s*'
        r'(?:=\s*([^;{]+))?;'
    )
    result = {}
    for header in headers:
        for m in pattern.finditer(header.read_text(errors='replace')):
            var_name = m.group(2).strip()
            if var_name not in result:
                result[var_name] = (m.group(1).strip(), m.group(3))
    return result


def build_type_alias_map(headers: list) -> dict:
    """Return {alias: full_cpp_type} from 'using Alias = FullType;' declarations."""
    pattern = re.compile(r'\busing\s+(\w+)\s*=\s*([^;]+);')
    result = {}
    for header in headers:
        for m in pattern.finditer(header.read_text(errors='replace')):
            result[m.group(1).strip()] = m.group(2).strip()
    return result


def resolve_parameters(raw_params: list, member_var_map: dict) -> list:
    params = []
    for name, member_var, description in raw_params:
        cpp_type, default_raw = member_var_map.get(member_var, ('', None))
        params.append(Parameter(
            name=name,
            ros_type=cpp_param_type(cpp_type),
            default=format_default(default_raw, cpp_type),
            description=description,
        ))
    return params


# ---------------------------------------------------------------------------
# Markdown rendering
# ---------------------------------------------------------------------------

def md_topic_table(interfaces: list) -> str:
    rows = ['| Topic | Type | Description |', '| --- | --- | --- |']
    rows += [f'| `{i.name}` | `{i.msg_type}` | |' for i in interfaces]
    return '\n'.join(rows)


def md_action_table(interfaces: list) -> str:
    rows = ['| Action | Type | Description |', '| --- | --- | --- |']
    rows += [f'| `{i.name}` | `{i.action_type}` | |' for i in interfaces]
    return '\n'.join(rows)


def md_launch_args_table(args: list) -> str:
    rows = ['| Argument | Default | Description |', '| --- | --- | --- |']
    rows += [f'| `{name}` | `{default}` | {description} |' for name, default, description in args]
    return '\n'.join(rows)


def render_launch_files(launch_files: list, repo_root: Path) -> str:
    parts = []
    for f in launch_files:
        section = [f'### [`{f.name}`]({f.relative_to(repo_root)})']
        args = extract_launch_arguments(f)
        if args:
            section += ['', md_launch_args_table(args)]
        parts.append('\n'.join(section))
    return '\n\n'.join(parts)


def md_parameter_table(params: list) -> str:
    rows = ['| Parameter | Type | Default | Description |', '| --- | --- | --- | --- |']
    rows += [f'| `{p.name}` | `{p.ros_type}` | `{p.default}` | {p.description} |'
             for p in params]
    return '\n'.join(rows)


def render_node(node: NodeInterfaces) -> str:
    parts = [f'## `{node.node_name}`']
    if node.subscribers:
        parts += ['\n### Subscribed Topics\n', md_topic_table(node.subscribers)]
    if node.publishers:
        parts += ['\n### Published Topics\n', md_topic_table(node.publishers)]
    if node.action_servers:
        parts += ['\n### Actions\n', md_action_table(node.action_servers)]
    if node.action_clients:
        parts += ['\n### Action Clients\n', md_action_table(node.action_clients)]
    if node.parameters:
        parts += ['\n### Parameters\n', md_parameter_table(node.parameters)]
    return '\n'.join(parts)


# ---------------------------------------------------------------------------
# README injection
# ---------------------------------------------------------------------------

AUTOGEN_HEADING = '## Auto-generated Package Documentation'


def normalize_key(cell: str) -> str:
    """Strip a table first-column value down to a plain name for dict lookup."""
    cell = cell.strip()
    m = re.match(r'\[`([^`]+)`\]\([^)]+\)', cell)
    if m:
        return m.group(1)
    m = re.match(r'`([^`]+)`', cell)
    if m:
        return m.group(1)
    return cell


def extract_existing_descriptions(text: str) -> dict:
    """Return {normalized_name: description} for every non-empty description cell in text."""
    descriptions = {}
    for line in text.splitlines():
        line = line.strip()
        if not (line.startswith('|') and line.endswith('|')):
            continue
        cells = [c.strip() for c in line.split('|')[1:-1]]
        if len(cells) < 2:
            continue
        if all(re.match(r'^-+$', c) for c in cells if c):  # separator row
            continue
        first = cells[0]
        if not (first.startswith('`') or first.startswith('[')):  # header row
            continue
        desc = cells[-1]
        if desc:
            descriptions[normalize_key(first)] = desc
    return descriptions


def fill_descriptions(generated: str, old: dict) -> str:
    """For each generated table row with an empty last cell, fill in the old description."""
    def replace(m):
        line = m.group(0)
        cells = [c.strip() for c in line.split('|')[1:-1]]
        if len(cells) < 2 or cells[-1]:
            return line
        desc = old.get(normalize_key(cells[0]), '')
        if desc:
            return re.sub(r'\| \|$', f'| {desc} |', line)
        return line
    return re.sub(r'^\|.*\|$', replace, generated, flags=re.MULTILINE)


def print_diff(old: str, new: str, path: Path) -> None:
    """Print a colored unified diff of old vs new to stderr."""
    RED, GREEN, CYAN, RESET = '\033[31m', '\033[32m', '\033[36m', '\033[0m'
    lines = list(difflib.unified_diff(
        old.splitlines(keepends=True),
        new.splitlines(keepends=True),
        fromfile=f'a/{path.name}',
        tofile=f'b/{path.name}',
    ))
    if not lines:
        sys.stderr.write('(no changes)\n')
        return
    for line in lines:
        if line.startswith('+') and not line.startswith('+++'):
            color = GREEN
        elif line.startswith('-') and not line.startswith('---'):
            color = RED
        elif line.startswith('@@'):
            color = CYAN
        else:
            color = ''
        sys.stderr.write(f'{color}{line}{RESET if color else ""}')


def shift_headings(text: str, offset: int) -> str:
    """Prefix every markdown heading line with `offset` extra # characters."""
    return re.sub(r'^(#+)', lambda m: '#' * (len(m.group(1)) + offset), text, flags=re.MULTILINE)


def update_readme(readme_path: Path, generated: str) -> None:
    """Insert `generated` under the auto-generated section, creating it if absent.

    Non-empty description cells written by the user are preserved across runs.
    """
    content = readme_path.read_text() if readme_path.exists() else ''
    generated = generated.rstrip() + '\n\n'  # ensure one trailing blank line
    section_pattern = re.compile(
        r'## Auto-generated Package Documentation\n(.*?)(?=\n## |\Z)',
        re.DOTALL,
    )
    if AUTOGEN_HEADING in content:
        m = section_pattern.search(content)
        if m:
            old_descriptions = extract_existing_descriptions(m.group(1))
            generated = fill_descriptions(generated, old_descriptions)
        block = f'{AUTOGEN_HEADING}\n\n{generated}'
        new_content = section_pattern.sub(block, content)
    else:
        new_content = content.rstrip() + f'\n\n{AUTOGEN_HEADING}\n\n{generated}'
    readme_path.write_text(new_content)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    repo_root = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).parent.parent

    packages = find_packages(repo_root)
    if not packages:
        print('No ROS packages found.', file=sys.stderr)
        sys.exit(1)

    output_blocks = []
    for pkg_name, pkg_dir in packages:
        node_sources = find_node_sources(pkg_dir)
        launch_files = find_launch_files(pkg_dir)
        if not node_sources and not launch_files:
            continue

        headers = find_headers(pkg_dir)
        member_var_map = build_member_var_map(headers)
        type_aliases = build_type_alias_map(headers)

        pkg_parts = [f'# `{pkg_name}`']

        if launch_files:
            pkg_parts += ['\n## Launch Files\n', render_launch_files(launch_files, repo_root)]

        for source_file in node_sources:
            source = source_file.read_text(errors='replace')
            node = NodeInterfaces(
                node_name=extract_node_name(source) or source_file.stem,
                subscribers=extract_subscribers(source, type_aliases),
                publishers=extract_publishers(source, type_aliases),
                action_servers=extract_action_servers(source, type_aliases),
                action_clients=extract_action_clients(source, type_aliases),
                parameters=resolve_parameters(extract_raw_parameters(source), member_var_map),
            )
            pkg_parts.append('\n' + render_node(node))

        output_blocks.append('\n'.join(pkg_parts))

    generated = shift_headings('\n\n'.join(output_blocks), 2)
    readme_path = repo_root / 'README.md'
    old_content = readme_path.read_text() if readme_path.exists() else ''
    update_readme(readme_path, generated)
    new_content = readme_path.read_text()
    sys.stderr.write(f'Updated {readme_path}\n')
    print_diff(old_content, new_content, readme_path)


if __name__ == '__main__':
    main()
