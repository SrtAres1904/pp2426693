import json
import re
import os
import logging
import time
import anthropic
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
if not ANTHROPIC_API_KEY:
    raise RuntimeError("ANTHROPIC_API_KEY environment variable is not set")

# Single client instance reused across all requests
_client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

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

    MAX_CHARS = 80_000
    truncated = len(paper_text) > MAX_CHARS
    if truncated:
        paper_text = paper_text[:MAX_CHARS] + "\n\n[Note: paper was truncated for processing]"
        logger.warning("Paper text truncated to %d characters", MAX_CHARS)

    logger.info("Sending %d characters to Claude", len(paper_text))
    start = time.monotonic()

    message = _client.messages.create(
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

    elapsed = time.monotonic() - start
    usage = message.usage
    logger.info(
        "Claude responded in %.2fs | input_tokens=%d output_tokens=%d",
        elapsed,
        usage.input_tokens,
        usage.output_tokens,
    )

    raw = message.content[0].text.strip()

    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        logger.warning("Direct JSON parse failed, attempting regex extraction")
        match = re.search(r"\{.*\}", raw, re.DOTALL)
        if match:
            return json.loads(match.group())
        logger.error("Could not parse LLM response as JSON. Raw response:\n%s", raw)
        raise ValueError(f"Could not parse LLM response as JSON. Raw response:\n{raw}")
