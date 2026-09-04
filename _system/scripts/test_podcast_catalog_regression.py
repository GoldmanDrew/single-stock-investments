#!/usr/bin/env python3
"""Tests for the build_insights podcast catalog preserve guard.

The case that motivates the date half of the guard is 2026-09-01. The weekly
refresh published 3,767 episodes ending 2026-08-29; its corpus push to the
research vault then lost a rebase race, so the vault stayed at 3,750. Nine
hours later the nightly intake-full rebuilt from that vault and republished
3,750 episodes ending 2026-08-21 -- a week of new material deleted by a lane
that believed it had succeeded. 3750/3767 is 0.9955, so the count ratio could
not have seen it, and did not.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "_system" / "scripts"))

import build_insights as bi  # noqa: E402


def rows(count: int, newest: str) -> list[dict]:
    """`count` episodes, the newest of which published on `newest`."""
    out = [{"published": "2026-01-01"} for _ in range(max(0, count - 1))]
    if count:
        out.append({"published": newest})
    return out


class PodcastCatalogRegressionTests(unittest.TestCase):
    def test_preserves_the_2026_09_01_clobber(self) -> None:
        preserve, reason = bi.should_preserve_podcast_catalog(
            rows(3767, "2026-08-29"), rows(3750, "2026-08-21")
        )
        self.assertTrue(preserve)
        self.assertIn("backwards", reason)

    def test_count_ratio_alone_would_have_missed_it(self) -> None:
        # Pins the premise of the test above. If the date half of the guard is
        # ever dropped, this is what says the ratio cannot cover for it.
        self.assertGreaterEqual(3750, int(3767 * bi.PODCAST_REGRESSION_RATIO))

    def test_preserves_on_count_collapse(self) -> None:
        preserve, reason = bi.should_preserve_podcast_catalog(
            rows(3767, "2026-08-29"), rows(2000, "2026-08-29")
        )
        self.assertTrue(preserve)
        self.assertIn("smaller catalog", reason)

    def test_allows_a_current_rebuild(self) -> None:
        preserve, _ = bi.should_preserve_podcast_catalog(
            rows(3750, "2026-08-21"), rows(3767, "2026-08-29")
        )
        self.assertFalse(preserve)

    def test_allows_an_unchanged_rebuild(self) -> None:
        preserve, _ = bi.should_preserve_podcast_catalog(
            rows(3750, "2026-08-21"), rows(3750, "2026-08-21")
        )
        self.assertFalse(preserve)

    def test_growth_outranks_a_date_regression(self) -> None:
        # An upstream retraction of the newest episode alongside real growth is
        # a prune, not a stale clone. Preserving on that would wedge the lane
        # shut until some other show happened to publish.
        preserve, _ = bi.should_preserve_podcast_catalog(
            rows(3750, "2026-08-29"), rows(3800, "2026-08-28")
        )
        self.assertFalse(preserve)

    def test_no_prior_catalog_never_preserves(self) -> None:
        preserve, reason = bi.should_preserve_podcast_catalog([], rows(10, "2026-08-01"))
        self.assertFalse(preserve)
        self.assertIn("no committed catalog", reason)

    def test_undated_rows_fall_back_to_the_count_check(self) -> None:
        prior = [{"episode_id": f"e{i}"} for i in range(100)]
        preserve, _ = bi.should_preserve_podcast_catalog(prior, list(prior))
        self.assertFalse(preserve)

    def test_empty_rebuild_is_caught_by_the_count_check(self) -> None:
        preserve, reason = bi.should_preserve_podcast_catalog(rows(3750, "2026-08-21"), [])
        self.assertTrue(preserve)
        self.assertIn("smaller catalog", reason)


if __name__ == "__main__":
    raise SystemExit(unittest.main())
