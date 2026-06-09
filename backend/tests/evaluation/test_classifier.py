"""
AI classifier effectiveness tests.

Runs each fixture through the real Claude API and measures:
  - Detection rate (recall) on dangerous emails
  - False positive rate on benign emails
  - Severity accuracy
  - Category accuracy
  - Per-category precision/recall

Run with real API:
    pytest tests/evaluation/test_classifier.py -v -s --tb=short

Skip if no API key:
    pytest tests/evaluation/test_classifier.py -v --skip-live
"""

import os
import json
import pytest
from dataclasses import dataclass
from typing import Optional

from tests.evaluation.fixtures import (
    ALL_BENIGN, ALL_DANGEROUS, ALL_FIXTURES,
    SELF_HARM, GROOMING, BULLYING, DRUGS_ALCOHOL, STRANGER_CONTACT, PERSONAL_INFO,
    EmailFixture,
)

# Skip all tests if ANTHROPIC_API_KEY not set
pytestmark = pytest.mark.skipif(
    not os.getenv("ANTHROPIC_API_KEY"),
    reason="ANTHROPIC_API_KEY not set — skipping live classifier tests",
)


# ─────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────

def run_fixture(fixture: EmailFixture) -> dict:
    from app.services.analysis import classify_email
    return classify_email(fixture.message)


def severity_detected(result: dict) -> bool:
    return result.get("severity", "none") != "none"


def severities_match(expected: str, actual: str) -> bool:
    """Allow one-tier deviation for severity (model nuance is acceptable)."""
    order = ["none", "low", "medium", "high", "critical"]
    if expected not in order or actual not in order:
        return False
    return abs(order.index(expected) - order.index(actual)) <= 1


# ─────────────────────────────────────────────
# Individual fixture tests
# ─────────────────────────────────────────────

@pytest.mark.parametrize("fixture", ALL_BENIGN, ids=[f.description for f in ALL_BENIGN])
def test_benign_no_false_positive(fixture: EmailFixture):
    """Benign emails must not trigger an alert."""
    result = run_fixture(fixture)
    assert result["severity"] == "none", (
        f"FALSE POSITIVE on: '{fixture.description}'\n"
        f"  Got severity={result['severity']} category={result['category']}\n"
        f"  Summary: {result.get('summary', '')}"
    )


@pytest.mark.parametrize("fixture", ALL_DANGEROUS, ids=[f.description for f in ALL_DANGEROUS])
def test_dangerous_detected(fixture: EmailFixture):
    """Dangerous emails must be detected (severity != none)."""
    result = run_fixture(fixture)
    assert result["severity"] != "none", (
        f"MISSED DETECTION on: '{fixture.description}'\n"
        f"  Expected severity={fixture.expected_severity}, got none\n"
        f"  Summary: {result.get('summary', '')}"
    )


@pytest.mark.parametrize("fixture", ALL_DANGEROUS, ids=[f.description for f in ALL_DANGEROUS])
def test_correct_category(fixture: EmailFixture):
    """Dangerous emails must be assigned the correct category."""
    result = run_fixture(fixture)
    if result["severity"] == "none":
        pytest.skip("Email not detected — category accuracy irrelevant")
    assert result["category"] == fixture.expected_category, (
        f"WRONG CATEGORY on: '{fixture.description}'\n"
        f"  Expected {fixture.expected_category}, got {result['category']}"
    )


@pytest.mark.parametrize("fixture", ALL_DANGEROUS, ids=[f.description for f in ALL_DANGEROUS])
def test_severity_within_one_tier(fixture: EmailFixture):
    """Severity must be within one tier of expected (model calibration test)."""
    result = run_fixture(fixture)
    if result["severity"] == "none":
        pytest.skip("Email not detected — severity accuracy irrelevant")
    assert severities_match(fixture.expected_severity, result["severity"]), (
        f"SEVERITY MISCALIBRATED on: '{fixture.description}'\n"
        f"  Expected {fixture.expected_severity}, got {result['severity']}"
    )


@pytest.mark.parametrize("fixture", ALL_DANGEROUS, ids=[f.description for f in ALL_DANGEROUS])
def test_confidence_above_threshold(fixture: EmailFixture):
    """Detected dangerous emails must have confidence above the fixture's minimum."""
    result = run_fixture(fixture)
    if result["severity"] == "none":
        pytest.skip("Email not detected — confidence irrelevant")
    assert float(result["confidence"]) >= fixture.min_confidence, (
        f"LOW CONFIDENCE on: '{fixture.description}'\n"
        f"  Got confidence={result['confidence']}, min={fixture.min_confidence}"
    )


@pytest.mark.parametrize("fixture", ALL_DANGEROUS, ids=[f.description for f in ALL_DANGEROUS])
def test_summary_is_non_empty(fixture: EmailFixture):
    """Every detected alert must include a non-empty parent-safe summary."""
    result = run_fixture(fixture)
    if result["severity"] == "none":
        pytest.skip("Email not detected")
    assert result.get("summary", "").strip(), (
        f"EMPTY SUMMARY on: '{fixture.description}'"
    )


# ─────────────────────────────────────────────
# Aggregate precision / recall report
# ─────────────────────────────────────────────

def test_precision_recall_report(capsys):
    """
    Runs the full fixture set and prints a precision/recall report.
    This test always passes — it's a reporting test, not a gate.
    """
    from app.services.analysis import classify_email

    results = []
    for fixture in ALL_FIXTURES:
        result = classify_email(fixture.message)
        results.append((fixture, result))

    # Overall metrics
    true_positives  = sum(1 for f, r in results if f.expected_severity != "none" and r["severity"] != "none")
    false_negatives = sum(1 for f, r in results if f.expected_severity != "none" and r["severity"] == "none")
    false_positives = sum(1 for f, r in results if f.expected_severity == "none" and r["severity"] != "none")
    true_negatives  = sum(1 for f, r in results if f.expected_severity == "none" and r["severity"] == "none")

    total_dangerous = true_positives + false_negatives
    total_benign    = false_positives + true_negatives

    recall    = true_positives / total_dangerous if total_dangerous else 0
    precision = true_positives / (true_positives + false_positives) if (true_positives + false_positives) else 0
    fp_rate   = false_positives / total_benign if total_benign else 0

    # Per-category recall
    category_sets = {
        "self_harm":              SELF_HARM,
        "grooming":               GROOMING,
        "bullying":               BULLYING,
        "drugs_alcohol":          DRUGS_ALCOHOL,
        "stranger_contact":       STRANGER_CONTACT,
        "personal_info_sharing":  PERSONAL_INFO,
    }

    print("\n" + "═" * 60)
    print("  OpenBark Classifier Effectiveness Report")
    print("═" * 60)
    print(f"\n  Overall")
    print(f"  {'Recall (detection rate)':<30} {recall:.1%}  ({true_positives}/{total_dangerous} dangerous emails detected)")
    print(f"  {'Precision':<30} {precision:.1%}")
    print(f"  {'False positive rate':<30} {fp_rate:.1%}  ({false_positives}/{total_benign} benign emails flagged)")
    print(f"  {'True negatives':<30} {true_negatives}/{total_benign}")

    print(f"\n  Per-category recall")
    for category, fixtures in category_sets.items():
        detected = sum(
            1 for f in fixtures
            for r in [next(r for ff, r in results if ff is f)]
            if r["severity"] != "none"
        )
        total = len(fixtures)
        pct = detected / total if total else 0
        bar = "█" * int(pct * 20) + "░" * (20 - int(pct * 20))
        print(f"  {category:<30} {bar} {pct:.0%} ({detected}/{total})")

    print(f"\n  False positives detail")
    fps = [(f, r) for f, r in results if f.expected_severity == "none" and r["severity"] != "none"]
    if fps:
        for f, r in fps:
            print(f"  ⚠  {f.description}")
            print(f"     → severity={r['severity']} category={r['category']} confidence={r['confidence']:.2f}")
            print(f"     → {r.get('summary', '')[:100]}")
    else:
        print("  ✓ No false positives")

    print(f"\n  Missed detections")
    fns = [(f, r) for f, r in results if f.expected_severity != "none" and r["severity"] == "none"]
    if fns:
        for f, r in fns:
            print(f"  ✗  {f.description} (expected {f.expected_severity})")
    else:
        print("  ✓ No missed detections")

    print("\n" + "═" * 60)

    # Soft assertions — these set the quality bar
    assert recall >= 0.85, f"Recall too low: {recall:.1%} (minimum 85%)"
    assert fp_rate <= 0.15, f"False positive rate too high: {fp_rate:.1%} (maximum 15%)"
