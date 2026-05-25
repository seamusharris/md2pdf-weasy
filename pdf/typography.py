"""
Typography rules for ASCII-to-Unicode conversion.

Converts plain ASCII conventions to proper typographic characters.
Applied to markdown content before HTML conversion, so source files
stay in clean ASCII while output gets proper typography.

Conversions:
    " -- "     ->  em dash
    "->"       ->  arrow
    "5m x 5m"  ->  multiplication sign
    "6-8"      ->  en dash (digit ranges)
    "text"     ->  curly double quotes
    don't      ->  curly apostrophe
    ...        ->  ellipsis
"""

import re

_TYPO_RULES = [
    (re.compile(r" -- "), " \u2014 "),
    (re.compile(r"->"), "\u2192"),
    (re.compile(r"(\d\w*)\s*x\s+(\d)"),
     lambda m: m.group(1) + " \u00d7 " + m.group(2)),
    (re.compile(r"(\d)-(\d)"),
     lambda m: m.group(1) + "\u2013" + m.group(2)),
    (re.compile(r'(?:^|(?<=\s)|(?<=\*)|(?<=\())\"(\S)'), lambda m: "\u201c" + m.group(1)),
    (re.compile(r'(\S)\"(?=\s|$|[,.\*\)\:]|$)'), lambda m: m.group(1) + "\u201d"),
    (re.compile(r"(\w)'(\w)"),
     lambda m: m.group(1) + "\u2019" + m.group(2)),
    (re.compile(r"(\w)'(\s|$|[,.])"),
     lambda m: m.group(1) + "\u2019" + m.group(2)),
    (re.compile(r"\.\.\."), "\u2026"),
]


def typographic_convert(text):
    """Convert ASCII typography to proper Unicode characters.

    Skips content inside HTML tags to avoid corrupting attributes.
    """
    if not isinstance(text, str):
        return text

    # Split on HTML tags, only apply rules to non-tag parts
    parts = re.split(r'(<[^>]+>)', text)
    for i, part in enumerate(parts):
        if not part.startswith('<'):
            for pattern, replacement in _TYPO_RULES:
                part = pattern.sub(replacement, part)
            parts[i] = part
    return ''.join(parts)
