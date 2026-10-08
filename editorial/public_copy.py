"""Keep editorial provenance internal, with clean reader-facing post copy."""

import re


def clean_public_copy(text):
    text = re.sub(r"(?im)(?:^|[ \t])(?:\*\*)?Sources?\s*:[^\n]*", "", text)
    text = re.sub(r"(?im)^\s*(?:image|photo)(?: credit| attribution| source)?\s*:[^\n]*", "", text)
    text = re.sub(r"(?i)The shop scenario is an illustrative exercise\.?|This is a practice exercise, not a claim about a particular product\.?|The following is our practice exercise, not a finding from that report\.?", "", text)
    text = re.sub(r"(?im)^\s*(?:This|The) (?:image|photo|scenario|example) is (?:an? )?(?:illustrative|stock|fictional)[^\n]*", "", text)
    text = re.sub(r"\n[ \t]*\n(?:[ \t]*\n)+", "\n\n", text)
    return text.strip()
