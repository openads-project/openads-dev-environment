#!/usr/bin/env python3
"""Generate a pie chart of git contributions grouped by email-host organization."""

import argparse
import io
import re
import subprocess
import sys
import tempfile
import urllib.request
from pathlib import Path
from urllib.parse import urlparse

import matplotlib.pyplot as plt
import matplotlib.image as mpimg
import yaml


def parse_shortlog(repo_path: str) -> list[tuple[int, str]]:
    """Run git shortlog and return list of (commit_count, email)."""
    result = subprocess.run(
        ["git", "shortlog", "-sne", "--all"],
        capture_output=True,
        text=True,
        cwd=repo_path,
        check=True,
    )
    entries = []
    pattern = re.compile(r"^\s*(\d+)\s+.+<(.+)>\s*$")
    for line in result.stdout.strip().splitlines():
        m = pattern.match(line)
        if m:
            entries.append((int(m.group(1)), m.group(2).strip().lower()))
    return entries


def extract_host(email: str) -> str:
    """Extract the host part from an email address."""
    parts = email.rsplit("@", 1)
    return parts[1] if len(parts) == 2 else "unknown"


def load_mapping(mapping_path: str | None) -> dict:
    """Load the email-host to organization mapping from a YAML file.

    Expected format:
        mapping:
          ika.rwth-aachen.de:
            name: ika - RWTH Aachen
            logo: logos/ika.png           # optional
          gmail.com:
            name: Personal
        options:                          # optional global chart options
          title: Contributions by Organization
          min_percent: 2.0                # groups below this % go into "Other"
          output: contribution_chart.png
    """
    if mapping_path is None or not Path(mapping_path).is_file():
        return {}
    with open(mapping_path, "r") as f:
        return yaml.safe_load(f) or {}


def group_by_org(
    entries: list[tuple[int, str]], mapping: dict
) -> dict[str, int]:
    """Aggregate commit counts by organization derived from email host."""
    host_map = mapping.get("mapping", {})
    org_commits: dict[str, int] = {}
    for count, email in entries:
        host = extract_host(email)
        # Walk up subdomains to find a mapping match
        org_name = None
        parts = host.split(".")
        for i in range(len(parts)):
            candidate = ".".join(parts[i:])
            if candidate in host_map:
                entry = host_map[candidate]
                org_name = entry if isinstance(entry, str) else entry.get("name", candidate)
                break
        if org_name is None:
            org_name = host
        org_commits[org_name] = org_commits.get(org_name, 0) + count
    return org_commits


def resolve_logo(logo_value: str | None, mapping_path: str | None) -> str | None:
    """Resolve a logo path relative to the mapping file's directory or download from URL."""
    if not logo_value:
        return None
    parsed = urlparse(logo_value)
    if parsed.scheme in ("http", "https"):
        suffix = Path(parsed.path).suffix or ".png"
        tmp = tempfile.NamedTemporaryFile(suffix=suffix, delete=False)
        urllib.request.urlretrieve(logo_value, tmp.name)
        return tmp.name
    p = Path(logo_value)
    if p.is_absolute() and p.is_file():
        return str(p)
    if mapping_path:
        candidate = Path(mapping_path).parent / logo_value
        if candidate.is_file():
            return str(candidate)
    if p.is_file():
        return str(p)
    return None


def get_org_logo_map(mapping: dict, mapping_path: str | None) -> dict[str, str]:
    """Build a map from org name -> resolved logo file path."""
    logo_map: dict[str, str] = {}
    for _host, entry in mapping.get("mapping", {}).items():
        if isinstance(entry, dict):
            name = entry.get("name", _host)
            logo_path = resolve_logo(entry.get("logo"), mapping_path)
            if logo_path:
                logo_map[name] = logo_path
    return logo_map


def read_logo_image(logo_file: str):
    """Read a logo image file, rasterizing SVGs via cairosvg."""
    if Path(logo_file).suffix.lower() == ".svg":
        import cairosvg
        png_data = cairosvg.svg2png(url=logo_file, output_width=256, output_height=256)
        return mpimg.imread(io.BytesIO(png_data), format="png")
    return mpimg.imread(logo_file)


def build_chart(
    org_commits: dict[str, int],
    logo_map: dict[str, str],
    options: dict,
    output_path: str,
) -> None:
    """Render a pie chart and save to disk."""
    title = options.get("title", "Contributions by Organization")
    min_percent = float(options.get("min_percent", 2.0))
    figsize_w = float(options.get("figsize_w", 8))
    figsize_h = float(options.get("figsize_h", 6))

    total = sum(org_commits.values())
    if total == 0:
        print("No commits found.", file=sys.stderr)
        sys.exit(1)

    # Collapse small slices into "Other"
    filtered: dict[str, int] = {}
    other = 0
    for org, count in org_commits.items():
        if (count / total) * 100 < min_percent:
            other += count
        else:
            filtered[org] = count
    if other > 0:
        filtered["Other"] = other

    # Sort descending
    sorted_orgs = sorted(filtered.items(), key=lambda x: x[1], reverse=True)
    labels = [org for org, _ in sorted_orgs]
    sizes = [count for _, count in sorted_orgs]

    # Build label strings with counts
    display_labels = [
        f"{label}"
        for label, size in zip(labels, sizes)
    ]

    # Color palette
    cmap = plt.get_cmap("tab20")
    colors = [cmap(i / max(len(labels), 1)) for i in range(len(labels))]

    fig, ax = plt.subplots(figsize=(figsize_w, figsize_h))
    wedges, texts = ax.pie(
        sizes,
        labels=display_labels,
        colors=colors,
        startangle=140,
        wedgeprops={"edgecolor": "white", "linewidth": 1.5},
    )

    # Replace text labels with logos where available, scaled by segment fraction
    import math
    from matplotlib.offsetbox import OffsetImage, AnnotationBbox

    max_zoom = 0.18
    min_zoom = 0.06
    for text, label, size in zip(texts, labels, sizes):
        logo_file = logo_map.get(label)
        if not logo_file:
            continue
        logo_img = read_logo_image(logo_file)
        fraction = size / total
        zoom = min_zoom + (max_zoom - min_zoom) * min(fraction / 0.5, 1.0)
        # Position the logo where the text label was
        x, y = text.get_position()
        text.set_visible(False)
        im = OffsetImage(logo_img, zoom=zoom)
        ab = AnnotationBbox(im, (x, y), frameon=False, box_alignment=(0.5, 0.5))
        ax.add_artist(ab)

    ax.set_title(title, fontsize=14, fontweight="bold", pad=20)
    fig.tight_layout()

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, dpi=150, bbox_inches="tight", transparent=False)
    plt.close(fig)
    print(f"Chart saved to {output_path}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate a pie chart of contributions per organization from git history."
    )
    parser.add_argument(
        "--repo",
        default=".",
        help="Path to the git repository (default: current directory).",
    )
    parser.add_argument(
        "--mapping",
        default=None,
        help="Path to a YAML mapping file (email host → org name/logo).",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="Output image path (default: contribution_chart.png).",
    )
    parser.add_argument(
        "--title",
        default=None,
        help="Chart title.",
    )
    parser.add_argument(
        "--min-percent",
        type=float,
        default=None,
        help="Minimum percentage to get its own slice; smaller ones become 'Other'.",
    )
    args = parser.parse_args()

    mapping = load_mapping(args.mapping)
    options = mapping.get("options", {})

    # CLI flags override YAML options
    if args.title is not None:
        options["title"] = args.title
    if args.min_percent is not None:
        options["min_percent"] = args.min_percent

    output_path = args.output or options.get("output", "contribution_chart.png")

    entries = parse_shortlog(args.repo)
    org_commits = group_by_org(entries, mapping)
    logo_map = get_org_logo_map(mapping, args.mapping)
    build_chart(org_commits, logo_map, options, output_path)


if __name__ == "__main__":
    main()
