EXPECTED_SECTIONS = [
    "Executive summary",
    "Key findings",
    "Risks and open questions",
    "Recommendations",
]


def validate_report(text: str) -> list[str]:
    missing = []
    lowered = text.lower()
    for section in EXPECTED_SECTIONS:
        if section.lower() not in lowered:
            missing.append(section)
    return missing
