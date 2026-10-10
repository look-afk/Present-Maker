"""Offline smoke test for JSON parsing and editable PPTX export."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from ai.client import extract_json
from presentation.export import create_pptx


def main():
    parsed = extract_json('```json\n{"title":"Test","slides":[{"title":"A"}]}\n```')
    assert parsed["title"] == "Test"
    out = Path("smoke_test_output.pptx")
    create_pptx("Test topic", "en", {
        "title": "Test presentation", "subtitle": "Offline test",
        "slides": [{"title": "A clear idea", "body": "This is a complete explanatory paragraph about the subject, with context, reasons, and consequences. It is intentionally written as connected prose instead of short bullet fragments so the reader can understand the point without a presenter.", "example": "For example, this case demonstrates how the idea works in practice.", "takeaway": "The key conclusion follows from the explanation.", "evidence": ["S1"], "visual": "diagram", "speaker_notes": "Notes", "highlight": "Takeaway"}],
    }, [], out)
    assert out.exists() and out.stat().st_size > 1000
    out.unlink()
    print("OK: JSON parsing and PPTX generation")


if __name__ == "__main__":
    main()
