"""Renders a `DailyDigest` as human-readable Markdown -- what actually lands
in an inbox/Slack channel/terminal every morning. Kept separate from
`engine.py` so the scoring logic and its presentation can change
independently (e.g. swapping in an HTML/email template later doesn't touch
how a person gets bucketed or scored).
"""

from __future__ import annotations

from .models import DailyDigest, PersonRecommendation


def render_markdown(digest: DailyDigest) -> str:
    lines: list[str] = [
        f"# Morning Recommendations — {digest.generated_at:%Y-%m-%d}",
        "",
        f"_{digest.considered_count} contact(s) with an active conversation signal considered._",
        "",
    ]

    if digest.top_pick:
        lines.append(f"**Top pick:** {_line(digest.top_pick)}")
        lines.append("")

    lines.append(_section("Contact today", digest.contact_today, show_message=True))
    lines.append(_section("Highest buying intent", digest.ranked_by_buying_intent[:10]))
    lines.append(_section("Hot", digest.hot))
    lines.append(_section("Cold", digest.cold))
    lines.append(_section("Ignore (resolved, stale, or low intent)", digest.ignore))

    return "\n".join(lines).strip() + "\n"


def _section(title: str, items: list[PersonRecommendation], *, show_message: bool = False) -> str:
    if not items:
        return f"## {title}\n\n_None today._\n"
    body = [f"## {title}", ""]
    for item in items:
        body.append(f"- {_line(item)}")
        if show_message:
            body.append(f"  - Suggested message: {item.best_message}")
    body.append("")
    return "\n".join(body)


def _line(item: PersonRecommendation) -> str:
    company = f" ({item.company_name})" if item.company_name else ""
    return (
        f"**{item.name}**{company} — score {item.buying_intent_score:.0f}, "
        f"{item.temperature.value.title()}, {item.interest_level.title()} interest, "
        f"{item.urgency.title()} urgency — {item.reason}"
    )
