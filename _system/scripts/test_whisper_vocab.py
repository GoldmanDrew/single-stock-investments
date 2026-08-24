import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import whisper_vocab as V


class HotwordBudgetTests(unittest.TestCase):
    """The cap is not advisory.

    faster_whisper's get_prompt truncates hotwords to `max_length // 2 - 1`
    tokens -- 223 for Whisper -- and does it silently. Overflowing does not
    error; it drops whatever sits past the cut, and because the packer puts
    episode-specific names first, an overflow would quietly discard the core
    finance terms rather than the low-value tail. Assert the budget instead.
    """

    def test_stays_inside_the_prompt_budget(self):
        crowded = ("$AAPL $MSFT $GOOGL $AMZN $META $NVDA $TSLA $BRK.B $JPM $V "
                   "with Mohnish Pabrai and Chris Hohn on Berkshire Hathaway")
        hot = V.build_hotwords(crowded, show_id="acquired", description=crowded * 4)
        self.assertLessEqual(len(hot), V.MAX_HOTWORD_CHARS)
        # 4 chars/token is the approximation the budget is set against; keep a
        # real margin under 223 so a name-dense string cannot cross it.
        self.assertLess(len(hot) / 4, 200)

    def test_core_terms_survive_a_crowded_title(self):
        crowded = " ".join(f"${t}" for t in
                           ("AAPL", "MSFT", "GOOGL", "AMZN", "META", "NVDA", "TSLA"))
        hot = V.build_hotwords(crowded)
        self.assertIn("EBITDA", hot)
        self.assertIn("free cash flow", hot)


class ResolutionTests(unittest.TestCase):
    def test_explicit_tickers_resolve_to_company_names(self):
        hot = V.build_hotwords("Portfolio update: $GTX, $MSB, $TPL")
        self.assertIn("Garrett Motion", hot)
        self.assertIn("Mesabi Trust", hot)
        self.assertIn("Texas Pacific Land", hot)

    def test_short_aliases_do_not_match_prose(self):
        """A two-letter ticker inside ordinary words is a false hotword.

        Biasing the decoder toward a word nobody said is worse than omitting it,
        so the alias index requires 5+ characters.
        """
        hot = V.build_hotwords("A conversation about being on the way to a better business")
        self.assertNotIn("Agilent", hot)

    def test_empty_input_still_returns_the_core(self):
        hot = V.build_hotwords("")
        self.assertIn("Nvidia", hot)
        self.assertTrue(hot)


class QueueRankingTests(unittest.TestCase):
    def test_in_book_beats_near_universe_beats_neither(self):
        self.assertTrue(V.in_book_hits("Portfolio update: $GTX, $MSB, $TPL"))
        self.assertFalse(V.in_book_hits("The a16z Podcast: a society under construction"))
        self.assertTrue(V.universe_hits("A roundtable on Angi $ANGI"))

    def test_ranking_is_not_quadratic(self):
        """Guards a real regression.

        The first version scanned every alias against every title -- roughly
        1,439 queue items x 20,000 aliases -- and hung the sort outright. The
        dict-and-n-grams version ranks the whole backlog in hundredths of a
        second. A second is already 30x slack; anything slower means the
        alias-per-item scan is back.
        """
        import time

        titles = [f"Episode {i} about Fastenal and $AAPL and other things" for i in range(2000)]
        V.in_book_hits("warm the cache")
        start = time.perf_counter()
        for title in titles:
            V.in_book_hits(title)
        self.assertLess(time.perf_counter() - start, 1.0)


if __name__ == "__main__":
    unittest.main()
