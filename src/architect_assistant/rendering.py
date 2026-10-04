from __future__ import annotations

from architect_assistant.models import Candidate, Specification, digest


def render_instructions(specification: Specification, candidate: Candidate) -> str:
    """Render an inspectable draft. Rendering never implies approval or publication."""
    if candidate.specification_hash != digest(specification):
        raise ValueError("Candidate belongs to a different specification")
    section_map = {section.rule_id: section for section in candidate.sections}
    if len(section_map) != len(candidate.sections) or set(section_map) != {
        rule.id for rule in specification.rules
    }:
        raise ValueError("Candidate must contain exactly one section for every rule")
    lines = [
        f"# Developer guidance: {specification.project}",
        "",
        "Status: draft. Instructions guide the coding tool; CI and access controls enforce rules.",
        f"Specification: {specification.version}; candidate revision: {candidate.revision}.",
        f"Specification hash: {candidate.specification_hash}",
        "",
        "## Source layers",
        "",
    ]
    for layer in sorted(specification.layers, key=lambda layer: (layer.kind, layer.id)):
        lines.append(f"- {layer.kind}: {layer.id}@{layer.version}")
    for rule in specification.rules:
        lines.extend(
            [
                "",
                f"## {rule.id}: {rule.title}",
                "",
                f"Strength: {rule.strength.upper()}. Source: {rule.source}",
                "",
                section_map[rule.id].text,
            ]
        )
        if rule.verification:
            lines.extend(["", "Suggested independent checks (not executed by this builder):"])
            lines.extend(f"- {check}" for check in rule.verification)
    if specification.references:
        lines.extend(["", "## Integration documentation", ""])
        for reference in sorted(specification.references, key=lambda ref: ref.id):
            lines.append(
                f"- {reference.id}: {reference.title} ({reference.version}): {reference.url} "
                f"— governed by {reference.permitted_by}."
            )
        lines.extend(["", "Documentation does not grant integration permissions."])
    return "\n".join(lines) + "\n"
