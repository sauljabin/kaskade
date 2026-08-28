import re

SVG_VIEWBOX = re.compile(r'(<svg\b)(?![^>]*\bwidth=)(?=[^>]*\bviewBox="0 0 ([\d.]+) ([\d.]+)")')


def normalize_svg(svg: str) -> str:
    """Add intrinsic dimensions and remove trailing whitespace from an SVG."""
    svg = SVG_VIEWBOX.sub(
        lambda match: (f'{match.group(1)} width="{match.group(2)}" height="{match.group(3)}"'),
        svg,
        count=1,
    )
    return "\n".join(line.rstrip() for line in svg.splitlines()) + "\n"
