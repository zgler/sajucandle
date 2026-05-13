"""E2E test: 실제 Claude API 호출로 감정서 생성."""
from __future__ import annotations

import asyncio
import json
import sys
import time

sys.stdout.reconfigure(encoding="utf-8")

from sajucandle.saju.report_context import collect_report_context
from sajucandle.saju.report_generator import generate_report


async def main():
    print("=== E2E Test: report generation ===")
    print("1) Collecting context...")
    ctx = collect_report_context(1996, 1, 23, 3, "M", 2026)
    print(f"   day_master: {ctx['day_master']}")
    print(f"   investor_type: {ctx['investor_type']}")
    print(f"   sewoon: {ctx['sewoon']}")
    print()

    print("2) Calling Claude API (claude-sonnet-4-6)...")
    start = time.time()
    sections = await generate_report(ctx)
    elapsed = time.time() - start
    print(f"   Completed in {elapsed:.1f}s")
    print(f"   Sections: {len(sections)}")
    print()

    for sec in sections:
        title = sec["title"]
        hl = sec["highlight"][:60]
        ct = sec["content"][:80]
        print(f"   [{sec['id']}] {title}")
        print(f"       highlight: {hl}...")
        print(f"       content: {ct}...")
        print()

    assert len(sections) == 7, f"Expected 7 sections, got {len(sections)}"
    for sec in sections:
        assert "id" in sec and "title" in sec and "content" in sec and "highlight" in sec
        assert len(sec["content"]) > 50, f"Section {sec['id']} content too short"
        assert len(sec["highlight"]) > 10, f"Section {sec['id']} highlight too short"

    print("=== ALL E2E CHECKS PASSED ===")

    with open("tests/e2e_report_output.json", "w", encoding="utf-8") as f:
        json.dump(sections, f, ensure_ascii=False, indent=2)
    print("Output saved to tests/e2e_report_output.json")


asyncio.run(main())
