"""Blockquote splitting and classification for markdown-to-PDF conversion.

Blockquote callout tiers (cool-to-warm):
    default     — #666 grey border, light grey background
    info        — #1e3a5f navy border, light navy background
    tip         — #1a7a6d teal border, light teal background
    important   — #6b3fa0 purple border, light purple background
    caution     — #946b00 amber border, light amber background
    warning     — #d94040 red border, light pink background

Domain-direction tiers (only styled by themes that define --color-up /
--color-down — currently regrading):
    up          — leading ▲ on the blockquote; promotion-direction callout
    down        — leading ▼ on the blockquote; demotion-direction callout
"""

import re


def split_merged_blockquotes(html):
    """Split blockquotes with multiple <p> children into separate blockquotes.

    Python-Markdown merges consecutive > lines (separated by blank lines) into
    a single <blockquote>. This restores them as individual elements so each
    gets its own border and spacing.
    """
    def splitter(match):
        inner = match.group(1)
        paragraphs = re.findall(r"<p>(.*?)</p>", inner, flags=re.DOTALL)
        if len(paragraphs) <= 1:
            return match.group(0)
        # Only split a blockquote that is *nothing but* <p> children. If it
        # also holds a list, table, or other block, splitting on paragraphs
        # alone would silently drop that content, so leave it intact.
        residue = re.sub(r"<p>.*?</p>", "", inner, flags=re.DOTALL).strip()
        if residue:
            return match.group(0)
        return "\n".join(
            f"<blockquote>\n<p>{p.strip()}</p>\n</blockquote>"
            for p in paragraphs
        )
    return re.sub(
        r"<blockquote>\s*(.*?)\s*</blockquote>", splitter, html, flags=re.DOTALL
    )


def classify_blockquotes(html, extra_keywords=None):
    """Add CSS classes to blockquotes based on content.

    Six-tier system with cool-to-warm colour progression:
      warning   — **Warning:**
      caution   — **Caution:** **Attention:**
      important — **Important:** **Key:** **Highlight:**
      tip       — **Tip:** **Success:**
      info      — **Note:** **Info:** (or plain text Note:)
      default   — class="default-aside", grey border + light grey background

    Also supports GitHub-style alert syntax (standard markdown, renders
    as visible text in basic renderers, styled in GitHub and our pipeline):

      > [!NOTE]
      > Content here

    Recognised types: NOTE, TIP, IMPORTANT, WARNING, CAUTION.

    Args:
        extra_keywords: Optional dict mapping tier name to list of additional
            bold keywords, e.g. ``{'warning': ['S1 risk'], 'info': ['S1 note']}``.
    """
    # Build keyword → tier mapping: defaults first, then extras
    _keyword_tiers = {
        'Warning': 'warning',
        'Caution': 'caution',
        'Attention': 'caution',
        'Important': 'important',
        'Key': 'important',
        'Highlight': 'important',
        'Tip': 'tip',
        'Success': 'tip',
        'Note': 'info',
        'Info': 'info',
    }
    if extra_keywords:
        for tier, keywords in extra_keywords.items():
            for kw in keywords:
                _keyword_tiers[kw] = tier

    # GitHub-style [!TYPE] → tier mapping
    _alert_tiers = {
        'NOTE': 'info',
        'TIP': 'tip',
        'IMPORTANT': 'important',
        'WARNING': 'warning',
        'CAUTION': 'caution',
    }

    def classify(match):
        content = match.group(1)

        # GitHub-style [!TYPE] at the start of blockquote content
        alert_match = re.search(
            r'<p>\s*\[!(NOTE|TIP|IMPORTANT|WARNING|CAUTION)\]\s*',
            content, re.IGNORECASE
        )
        if alert_match:
            tier = _alert_tiers[alert_match.group(1).upper()]
            # Remove the [!TYPE] marker from the content
            cleaned = content[:alert_match.start()] + \
                content[alert_match.start():alert_match.end()].replace(
                    alert_match.group(0), '<p>', 1) + \
                content[alert_match.end():]
            return f'<blockquote class="{tier}">{cleaned}</blockquote>'

        # Check bold keywords against the tier map
        for keyword, tier in _keyword_tiers.items():
            pattern = rf"<strong>\s*{re.escape(keyword)}\s*:?\s*</strong>"
            if re.search(pattern, content, re.IGNORECASE):
                return f'<blockquote class="{tier}">{content}</blockquote>'

        # Direction-arrow fallback — ▲ / ▼ at the start of the
        # blockquote. Only fires when no keyword matched, so
        # `> ▼ **Warning:** ...` still gets warning styling. The
        # arrow is preserved in the rendered text; the class is what
        # themes hook into. Themes that define --color-up / --color-down
        # (currently regrading) provide the colour; otherwise the class
        # is a no-op.
        arrow_match = re.match(r'\s*<p>\s*([▲▼])', content)
        if arrow_match:
            tier = 'up' if arrow_match.group(1) == '▲' else 'down'
            return f'<blockquote class="{tier}">{content}</blockquote>'

        # Info tier — plain text fallback (schedule compatibility)
        text = re.sub(r'<[^>]+>', '', content).strip()
        if text.startswith('Note:') or text.startswith('\u26a0'):
            return f'<blockquote class="info">{content}</blockquote>'

        # Default tier — grey border + light grey background
        return f'<blockquote class="default-aside">{content}</blockquote>'

    return re.sub(
        r"<blockquote>(.*?)</blockquote>", classify, html, flags=re.DOTALL
    )
