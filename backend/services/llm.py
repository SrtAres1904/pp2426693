import json
import re
import os
import anthropic
from dotenv import load_dotenv

load_dotenv()

# ─────────────────────────────────────────────────────────────
# PUT YOUR ANTHROPIC API KEY HERE  ↓  (or set it in .env file)
# ─────────────────────────────────────────────────────────────
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "sk-ant-XXXXXXXXXXXXXXXX")  # <-- replace with your key from https://console.anthropic.com/

SYSTEM_PROMPT = """You are an expert academic research assistant specialising in analysing scientific papers.

Given the full text (or an excerpt) of a research paper, extract the following information and return it as a **valid JSON object** — nothing else, no markdown fences, no commentary.

JSON schema:
{
  "title": "The paper's title if found, otherwise 'Untitled Paper'",
  "objective": "2-3 sentence description of the research question or objective",
  "methodology": "2-3 sentences describing how the research was conducted (methods, datasets, tools)",
  "key_findings": [
    "Specific finding 1",
    "Specific finding 2",
    "Specific finding 3",
    "Specific finding 4",
    "Specific finding 5"
  ],
  "conclusions": "2-3 sentences on what the findings mean and their broader implications",
  "novel_contributions": [
    "Novel contribution or innovation 1",
    "Novel contribution or innovation 2",
    "Novel contribution or innovation 3"
  ],
  "limitations": [
    "Limitation 1",
    "Limitation 2"
  ],
  "keywords": ["keyword1", "keyword2", "keyword3", "keyword4", "keyword5"],
  "summary": "A concise single-paragraph summary of the entire paper suitable for an abstract replacement"
}

Rules:
- Be precise, academic, and factual.
- Extract information directly from the paper; do NOT fabricate.
- If a section is absent from the paper, make a reasonable inference and note it briefly.
- Return ONLY the JSON object."""


def generate_highlights(paper_text: str) -> dict:
    """Call Claude to generate structured research highlights from paper text."""

    # Truncate extremely long papers to stay within context limits
    MAX_CHARS = 80_000
    if len(paper_text) > MAX_CHARS:
        paper_text = paper_text[:MAX_CHARS] + "\n\n[Note: paper was truncated for processing]"

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=2048,
        system=SYSTEM_PROMPT,
        messages=[
            {
                "role": "user",
                "content": (
                    "Please analyse this research paper and generate structured key highlights:\n\n"
                    + paper_text
                ),
            }
        ],
    )

    raw = message.content[0].text.strip()

    # Parse JSON — fall back to regex extraction if the model adds any wrapper text
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", raw, re.DOTALL)
        if match:
            return json.loads(match.group())
        raise ValueError(f"Could not parse LLM response as JSON. Raw response:\n{raw}")
