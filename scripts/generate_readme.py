#!/usr/bin/env python3
"""
Auto-generates ROS2 interface documentation (topics, actions, parameters)
by parsing C++ source files in a ROS2 repository and writing full package
README.md files next to package.xml.

Usage:
    python3 scripts/generate_readme.py [REPO_ROOT]

REPO_ROOT defaults to the script's parent directory.
The READMEs generated are <package_dir>/README.md for discovered ROS packages.
"""

import difflib
import re
import subprocess
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Optional
from xml.etree import ElementTree

try:
    from jinja2 import Environment, FileSystemLoader, TemplateNotFound
except ModuleNotFoundError as exc:
    if exc.name == 'jinja2':
        Environment = None
        FileSystemLoader = None
        TemplateNotFound = Exception
    else:
        raise


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
class ServiceInterface:
    name: str
    srv_type: str


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
    service_servers: list = field(default_factory=list)
    action_servers: list = field(default_factory=list)
    action_clients: list = field(default_factory=list)
    parameters: list = field(default_factory=list)


@dataclass
class RepoMetadata:
    owner: str
    repo: str
    owner_lower: str
    pages_url: str
    repo_https_url: str
    container_image: str


@dataclass
class PackageSection:
    title: str
    body: str


@dataclass
class PackageTemplateContext:
    package_name: str
    package_description: str
    toc_lines: list[str]
    sections: list[PackageSection]


@dataclass
class PackageDocEntry:
    name: str
    path: str


@dataclass
class TopLevelTemplateContext:
    repo_name: str
    owner: str
    pages_url: str
    repo_https_url: str
    container_image: str
    badges_block: str
    intro_block: str
    quickstart_package: str
    quickstart_launch_file: str
    documentation_lines: list[str]
    acknowledgements_body: str


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
    return default_str.strip()


# ---------------------------------------------------------------------------
# Discovery
# ---------------------------------------------------------------------------

def find_packages(repo_root: Path) -> list:
    """Return [(package_name, package_dir, package_description)] for ROS packages."""
    packages = []
    for pkg_xml in sorted(repo_root.rglob('package.xml')):
        try:
            root = ElementTree.parse(pkg_xml).getroot()
            name_el = root.find('name')
            description_el = root.find('description')
            if name_el is not None and name_el.text:
                description = ''
                if description_el is not None and description_el.text:
                    description = ' '.join(description_el.text.split())
                packages.append((name_el.text.strip(), pkg_xml.parent, description))
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


def find_interface_files(package_dir: Path, subdir: str, ext: str) -> list:
    """Return sorted list of interface definition files in package_dir/subdir/."""
    iface_dir = package_dir / subdir
    if not iface_dir.is_dir():
        return []
    return sorted(iface_dir.glob(f'*.{ext}'))


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


def extract_service_servers(source: str, aliases: dict) -> list:
    return [
        ServiceInterface(name=m.group(2), srv_type=cpp_ros_type(m.group(1), aliases))
        for m in re.finditer(r'create_service\s*<([^>]+)>\s*\(\s*"([^"]+)"', source)
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
            default = f'"{dv_m.group(1)}"'
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
            f'"{default_m.group(1)}"' if default_m else '',
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


def md_service_table(interfaces: list) -> str:
    rows = ['| Service | Type | Description |', '| --- | --- | --- |']
    rows += [f'| `{i.name}` | `{i.srv_type}` | |' for i in interfaces]
    return '\n'.join(rows)


def md_launch_args_table(args: list) -> str:
    rows = ['| Argument | Default | Description |', '| --- | --- | --- |']
    rows += [f'| `{name}` | `{default}` | {description} |' for name, default, description in args]
    return '\n'.join(rows)


def md_interface_table(entries: list) -> str:
    rows = ['| Type | Description |', '| --- | --- |']
    rows += [f'| [`{full_type}`]({rel_path}) | |' for full_type, rel_path in entries]
    return '\n'.join(rows)


def render_launch_files(launch_files: list, doc_root: Path) -> str:
    parts = []
    for f in launch_files:
        section = [f'### [`{f.name}`]({f.relative_to(doc_root)})']
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


def render_node_diagram(node: NodeInterfaces) -> str:
    """Return a Mermaid flowchart showing the node's pub/sub/action interfaces."""
    def q(s: str) -> str:
        return s.replace('"', "'")

    lines = ['```mermaid', 'flowchart LR']
    lines.append(f'    NODE("{q(node.node_name)}")')
    for i, s in enumerate(node.subscribers):
        lines.append(f'    S{i}:::hidden -->|{q(s.name)}| NODE')
    for i, ss in enumerate(node.service_servers):
        lines.append(f'    SS{i}:::hidden o--o|{q(ss.name)}| NODE')
    for i, p in enumerate(node.publishers):
        lines.append(f'    NODE -->|{q(p.name)}| P{i}:::hidden')
    for i, a in enumerate(node.action_servers):
        lines.append(f'    AS{i}:::hidden o-.-o|{q(a.name)}| NODE')
    lines.append('    classDef hidden display: none;')
    lines.append('```')
    return '\n'.join(lines)


def render_node(node: NodeInterfaces) -> str:
    parts = [f'### `{node.node_name}`']
    if node.subscribers or node.publishers or node.service_servers or node.action_servers:
        parts += ['', render_node_diagram(node)]
    if node.subscribers:
        parts += ['\n#### Subscribed Topics\n', md_topic_table(node.subscribers)]
    if node.publishers:
        parts += ['\n#### Published Topics\n', md_topic_table(node.publishers)]
    if node.service_servers:
        parts += ['\n#### Service Servers\n', md_service_table(node.service_servers)]
    if node.action_servers:
        parts += ['\n#### Action Servers\n', md_action_table(node.action_servers)]
    if node.action_clients:
        parts += ['\n#### Action Clients\n', md_action_table(node.action_clients)]
    if node.parameters:
        parts += ['\n#### Parameters\n', md_parameter_table(node.parameters)]
    return '\n'.join(parts)


def print_diff(old: str, new: str, path: Path) -> None:
    """Print a colored unified diff of old vs new to stderr."""
    RED, GREEN, CYAN, RESET = '\033[31m', '\033[32m', '\033[36m', '\033[0m'
    lines = list(difflib.unified_diff(
        old.splitlines(keepends=True),
        new.splitlines(keepends=True),
        fromfile=f'a/{path}',
        tofile=f'b/{path}',
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


def render_toc(node_names: list, has_launch_files: bool) -> str:
    entries = []
    if node_names:
        entries.append('- [Nodes](#nodes)')
        entries += [f'  - [{name}](#{name})' for name in node_names]
    if has_launch_files:
        entries.append('- [Launch Files](#launch-files)')
    return '\n'.join(entries)


def render_package_readme(
    template_env: Environment,
    package_name: str,
    package_description: str,
    toc_lines: list[str],
    sections: list[PackageSection],
) -> str:
    context = PackageTemplateContext(
        package_name=package_name,
        package_description=package_description,
        toc_lines=toc_lines,
        sections=sections,
    )
    rendered = render_template(
        template_env,
        'package_readme.md.j2',
        asdict(context),
    )
    return rendered.rstrip() + '\n'


# ---------------------------------------------------------------------------
# Top-level README rendering
# ---------------------------------------------------------------------------

INTRO_PLACEHOLDER = (
    '**TODO: Repository tagline/description**\n\n'
    'TODO: High-level repository introduction paragraph'
)

ACK_PLACEHOLDER = 'TODO: Project/funding acknowledgements'


def build_template_environment() -> Environment:
    if Environment is None or FileSystemLoader is None:
        raise RuntimeError(
            'Missing dependency: jinja2. Install with '
            '`pip install -r .openads-dev-environment/scripts/requirements.txt`.'
        )
    templates_dir = Path(__file__).resolve().parent / 'templates'
    return Environment(
        loader=FileSystemLoader(str(templates_dir)),
        autoescape=False,
        keep_trailing_newline=True,
        trim_blocks=False,
        lstrip_blocks=False,
    )


def render_template(template_env: Environment, template_name: str, context: dict) -> str:
    try:
        template = template_env.get_template(template_name)
    except TemplateNotFound as exc:
        raise RuntimeError(f'Missing template: {template_name}') from exc
    return template.render(**context)


def get_origin_remote(repo_root: Path) -> str:
    """Return origin remote URL for the repository, or raise on failure."""
    return subprocess.check_output(
        ['git', 'remote', 'get-url', 'origin'],
        cwd=repo_root,
        stderr=subprocess.DEVNULL,
        text=True,
    ).strip()


def parse_github_remote(remote: str) -> RepoMetadata:
    """Extract owner/repo metadata from GitHub-style remote URL."""
    m = re.search(r'github\.com[:/]([^/]+)/([^/]+?)(?:\.git)?$', remote)
    if not m:
        raise ValueError(f'Unsupported origin remote URL: {remote}')
    owner, repo = m.group(1), m.group(2)
    owner_lower = owner.lower()
    return RepoMetadata(
        owner=owner,
        repo=repo,
        owner_lower=owner_lower,
        pages_url=f'https://{owner_lower}.github.io/{repo}',
        repo_https_url=f'https://github.com/{owner}/{repo}',
        container_image=f'ghcr.io/{owner_lower}/{repo}:latest',
    )


def extract_intro_block(readme_text: str) -> str:
    """Return repo-specific intro block (headline + paragraph) or placeholder."""
    m = re.search(r'</p>\n\n(.*?)\n\n> \[!IMPORTANT\]', readme_text, re.DOTALL)
    if m and m.group(1).strip():
        return m.group(1).strip()
    return INTRO_PLACEHOLDER


def extract_acknowledgements_body(readme_text: str) -> str:
    """Return repo-specific acknowledgements body or placeholder."""
    m = re.search(r'^## 🙏 Acknowledgements\n\n(.*)\Z', readme_text, re.DOTALL | re.MULTILINE)
    if m and m.group(1).strip():
        return m.group(1).rstrip()
    return ACK_PLACEHOLDER


def render_badges(meta: RepoMetadata) -> str:
    return (
        '<p align="center">\n'
        f'  <a href="https://github.com/{meta.owner_lower}"><img src="https://img.shields.io/badge/OpenADS-ffff00"/></a>\n'
        f'  <a href="{meta.repo_https_url}/releases/latest"><img src="https://img.shields.io/github/v/release/{meta.owner}/{meta.repo}"/></a>\n'
        f'  <a href="{meta.repo_https_url}/blob/main/LICENSE"><img src="https://img.shields.io/github/license/{meta.owner}/{meta.repo}"/></a>\n'
        '  <a href="https://www.ros.org"><img src="https://img.shields.io/badge/ROS 2-jazzy-22314e"/></a>\n'
        '  <br>\n'
        f'  <a href="{meta.repo_https_url}/actions/workflows/docker-ros.yml"><img src="{meta.repo_https_url}/actions/workflows/docker-ros.yml/badge.svg"/></a>\n'
        f'  <a href="{meta.repo_https_url}/actions/workflows/industrial_ci.yml"><img src="{meta.repo_https_url}/actions/workflows/industrial_ci.yml/badge.svg"/></a>\n'
        f'  <a href="https://{meta.owner}.github.io/{meta.repo}"><img src="{meta.repo_https_url}/actions/workflows/docs.yml/badge.svg"/></a>\n'
        '</p>'
    )


def build_package_doc_entries(repo_root: Path, packages: list) -> list[PackageDocEntry]:
    entries = []
    for pkg_name, pkg_dir, _ in sorted(packages, key=lambda p: p[0]):
        rel_readme = (pkg_dir / 'README.md').relative_to(repo_root).as_posix()
        entries.append(PackageDocEntry(name=pkg_name, path=rel_readme))
    return entries


def build_documentation_lines(
    repo_root: Path,
    pages_url: str,
    package_doc_entries: list[PackageDocEntry],
) -> list[str]:
    lines = []
    implementation_details = repo_root / 'docs' / 'IMPLEMENTATION.md'
    if implementation_details.exists():
        lines.append('- [Implementation Details](./docs/IMPLEMENTATION.md)')
    lines.append(f'- [Source Code Documentation]({pages_url})')
    lines.append('- Package Documentation')
    for entry in package_doc_entries:
        lines.append(f'  - [{entry.name}]({entry.path})')
    return lines


def pick_quickstart_target(packages: list) -> tuple[str, str]:
    """Choose package and launch file for quick start launch command."""
    for pkg_name, pkg_dir, _ in sorted(packages, key=lambda p: p[0]):
        launch_files = find_launch_files(pkg_dir)
        if launch_files:
            return pkg_name, launch_files[0].name
    return 'PACKAGE_NAME', 'LAUNCH_FILE'


def render_top_level_readme(
    template_env: Environment,
    repo_root: Path,
    packages: list,
    existing_readme: str,
) -> str:
    remote = get_origin_remote(repo_root)
    meta = parse_github_remote(remote)
    intro_block = extract_intro_block(existing_readme)
    ack_body = extract_acknowledgements_body(existing_readme)
    quickstart_pkg, quickstart_launch_file = pick_quickstart_target(packages)
    package_doc_entries = build_package_doc_entries(repo_root, packages)
    documentation_lines = build_documentation_lines(repo_root, meta.pages_url, package_doc_entries)
    context = TopLevelTemplateContext(
        repo_name=meta.repo,
        owner=meta.owner,
        pages_url=meta.pages_url,
        repo_https_url=meta.repo_https_url,
        container_image=meta.container_image,
        badges_block=render_badges(meta),
        intro_block=intro_block,
        quickstart_package=quickstart_pkg,
        quickstart_launch_file=quickstart_launch_file,
        documentation_lines=documentation_lines,
        acknowledgements_body=ack_body,
    )
    rendered = render_template(
        template_env,
        'top_level_readme.md.j2',
        asdict(context),
    )
    return rendered.rstrip() + '\n'


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    repo_root = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).parent.parent
    try:
        template_env = build_template_environment()
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        sys.exit(2)

    packages = find_packages(repo_root)
    if not packages:
        print('Warning: no ROS packages found.', file=sys.stderr)

    for pkg_name, pkg_dir, pkg_description in packages:
        msgs = find_interface_files(pkg_dir, 'msg', 'msg')
        srvs = find_interface_files(pkg_dir, 'srv', 'srv')
        actions = find_interface_files(pkg_dir, 'action', 'action')
        node_sources = find_node_sources(pkg_dir)
        launch_files = find_launch_files(pkg_dir)

        sections = []
        nodes = []

        if msgs:
            entries = [(f'{pkg_name}/msg/{f.stem}', f.relative_to(pkg_dir)) for f in msgs]
            sections.append(PackageSection(title='Messages', body=md_interface_table(entries)))
        if srvs:
            entries = [(f'{pkg_name}/srv/{f.stem}', f.relative_to(pkg_dir)) for f in srvs]
            sections.append(PackageSection(title='Services', body=md_interface_table(entries)))
        if actions:
            entries = [(f'{pkg_name}/action/{f.stem}', f.relative_to(pkg_dir)) for f in actions]
            sections.append(PackageSection(title='Actions', body=md_interface_table(entries)))

        if node_sources or launch_files:
            headers = find_headers(pkg_dir)
            member_var_map = build_member_var_map(headers)
            type_aliases = build_type_alias_map(headers)

            for source_file in node_sources:
                source = source_file.read_text(errors='replace')
                node = NodeInterfaces(
                    node_name=extract_node_name(source) or source_file.stem,
                    subscribers=extract_subscribers(source, type_aliases),
                    publishers=extract_publishers(source, type_aliases),
                    service_servers=extract_service_servers(source, type_aliases),
                    action_servers=extract_action_servers(source, type_aliases),
                    action_clients=extract_action_clients(source, type_aliases),
                    parameters=resolve_parameters(extract_raw_parameters(source), member_var_map),
                )
                nodes.append(node)

            if nodes:
                node_parts = []
                for idx, node in enumerate(nodes):
                    if idx > 0:
                        node_parts.append('')
                    node_parts.append(render_node(node))
                sections.append(PackageSection(title='Nodes', body='\n'.join(node_parts)))

            if launch_files:
                sections.append(
                    PackageSection(title='Launch Files', body=render_launch_files(launch_files, pkg_dir))
                )

        toc = render_toc([node.node_name for node in nodes], bool(launch_files))
        toc_lines = toc.splitlines() if toc else []
        readme_path = pkg_dir / 'README.md'
        old_content = readme_path.read_text() if readme_path.exists() else ''
        new_content = render_package_readme(
            template_env=template_env,
            package_name=pkg_name,
            package_description=pkg_description,
            toc_lines=toc_lines,
            sections=sections,
        )
        readme_path.write_text(new_content)
        sys.stderr.write(f'Updated {readme_path}\n')
        print_diff(old_content, new_content, readme_path)

    root_readme_path = repo_root / 'README.md'
    old_root_readme = root_readme_path.read_text() if root_readme_path.exists() else ''
    new_root_readme = render_top_level_readme(template_env, repo_root, packages, old_root_readme)
    root_readme_path.write_text(new_root_readme)
    sys.stderr.write(f'Updated {root_readme_path}\n')
    print_diff(old_root_readme, new_root_readme, root_readme_path)


if __name__ == '__main__':
    main()
