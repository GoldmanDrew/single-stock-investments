import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from transcript_names import core_name, expected_names, repair


class CoreNameTests(unittest.TestCase):
    def test_strips_corporate_suffixes(self):
        self.assertEqual(core_name("UnitedHealth Group"), "UnitedHealth")
        self.assertEqual(core_name("FRMO Corporation"), "FRMO")
        self.assertEqual(core_name("Texas Pacific Land Corporation"), "Texas Pacific Land")

    def test_leaves_a_bare_name_alone(self):
        self.assertEqual(core_name("Fastenal"), "Fastenal")
        self.assertEqual(core_name("Sherwin-Williams"), "Sherwin-Williams")


class RepairTests(unittest.TestCase):
    def test_repairs_the_measured_fastenal_variants(self):
        """The real spellings Whisper produced for one episode.

        Three of these four clear the 0.80 floor. "Fastenor" (0.750) does not,
        and neither do Farsonal, Farsenil, Farsen or Farson -- roughly eight of
        the twenty-six mangled mentions in that episode stay mangled.

        That recall loss is deliberate. The floor sat at 0.72 first and let
        India/NVIDIA (0.727) through, rewriting a country into a chipmaker. A
        missed mention costs one lost citation; an invented one attributes a
        claim to a company nobody discussed, and that flows into the book.
        Precision wins. Recall here wants a different signal than edit distance
        -- corpus-wide token frequency would separate a real word from a mangle
        far better than similarity does.
        """
        text = ("Fastenel is a distributor. Later Fastenol grew, and Farsenal "
                "expanded again while Fastenor consolidated.")
        fixed, counts = repair(text, ["Fastenal"])
        self.assertEqual(fixed.count("Fastenal"), 3)
        self.assertEqual(counts, {"Fastenal": 3})
        self.assertIn("Fastenor", fixed)

    def test_rejoins_a_name_the_model_split(self):
        """`base` wrote "United Health" 85 times and "UnitedHealth" zero times."""
        text = "United Health reported. Analysts like United Health this year."
        fixed, counts = repair(text, ["UnitedHealth Group"])
        self.assertEqual(fixed.count("UnitedHealth"), 2)
        self.assertNotIn("United Health ", fixed)
        self.assertEqual(counts, {"UnitedHealth": 2})

    def test_does_not_rewrite_an_ordinary_given_name(self):
        """The regression that made phrase matching necessary.

        Component-wise matching turned a bare "William" into "Williams" and so
        invented a Sherwin-Williams mention out of a person. Only the full
        phrase may match.
        """
        text = "William joined the board. Later William sold his stake."
        fixed, counts = repair(text, ["Sherwin-Williams"])
        self.assertEqual(fixed, text)
        self.assertEqual(counts, {})

    def test_repairs_the_phrase_but_not_its_parts(self):
        text = "Sherwin-Willian is huge, and Sherman Williams too. William watched."
        fixed, _ = repair(text, ["Sherwin-Williams"])
        self.assertEqual(fixed.count("Sherwin-Williams"), 2)
        self.assertIn("William watched", fixed)

    def test_leaves_lowercase_common_words_alone(self):
        """A fastener distributor says "fastener" constantly. None may move."""
        text = "Each fastener and fasteners shipped; fastening matters. Fastenel grew."
        fixed, counts = repair(text, ["Fastenal"])
        self.assertIn("fastener and fasteners", fixed)
        self.assertIn("fastening matters", fixed)
        self.assertEqual(counts, {"Fastenal": 1})

    def test_a_capitalised_real_word_is_protected_by_its_lowercase_twin(self):
        text = "Fastening the panel. fastening again, and fastening once more."
        fixed, counts = repair(text, ["Fastenal"])
        self.assertEqual(fixed, text)
        self.assertEqual(counts, {})

    def test_unrelated_companies_are_untouched(self):
        text = "Microsoft and Salesforce both reported. Nvidia did too."
        fixed, counts = repair(text, ["Fastenal"])
        self.assertEqual(fixed, text)
        self.assertEqual(counts, {})

    def test_no_expected_names_is_a_no_op(self):
        text = "Fastenel grew."
        self.assertEqual(repair(text, [])[0], text)
        self.assertEqual(repair("", ["Fastenal"])[0], "")


class FalsePositiveGuardTests(unittest.TestCase):
    """Every case here was produced by a real dry run over the corpus.

    The first pass rewrote 1,447 spans across 94 transcripts and most were
    wrong: 272 to "THERE", 246 to "NVIDIA", 82 to "RIGHT", 81 to "Amazon.com".
    A silent name rewrite invents a company mention, so these stay covered.
    """

    def test_case_only_differences_are_left_alone(self):
        text = "Nvidia beat again, and Nvidia guided higher."
        fixed, counts = repair(text, ["NVIDIA Corporation"])
        self.assertEqual(fixed, text)
        self.assertEqual(counts, {})

    def test_a_registered_company_is_never_rewritten_into_another(self):
        """"Amazon" is its own registered name, not a mangled "Amazon.com"."""
        text = "Amazon competes with them on distribution."
        fixed, counts = repair(text, ["Amazon.com"])
        self.assertEqual(fixed, text)
        self.assertEqual(counts, {})

    def test_possessives_survive_the_rewrite(self):
        """Deleting the "'s" corrupted 45 spans in one episode.

        `_TOKEN` carries the apostrophe so O'Reilly stays one token, which meant
        "Amphenol's" matched whole and was replaced by a bare "Amphenol" --
        turning "Amphenol's margins" into "Amphenol margins".
        """
        text = "Amphenal's margins rose and Amphenel's did too."
        fixed, counts = repair(text, ["Amphenol"])
        self.assertEqual(fixed, "Amphenol's margins rose and Amphenol's did too.")
        self.assertEqual(counts, {"Amphenol": 2})

    def test_a_country_is_not_a_chipmaker(self):
        """India/NVIDIA scores 0.727 and a 0.72 threshold let it through."""
        text = "India is a large market. Nvidia is larger."
        fixed, counts = repair(text, ["NVIDIA Corporation"])
        self.assertEqual(fixed, text)
        self.assertEqual(counts, {})

    def test_an_ordinary_word_is_not_a_chipmaker_either(self):
        """Integral/Intel scores 0.769, also under the 0.80 floor."""
        text = "Integral parts matter. Intel ships them."
        fixed, counts = repair(text, ["Intel"])
        self.assertEqual(fixed, text)
        self.assertEqual(counts, {})

    def test_genuine_variants_still_clear_the_higher_floor(self):
        """The lowest true positive measured was Kostar/CoStar at 0.833."""
        text = "Kostar and Co-Star and Coastar all reported."
        fixed, counts = repair(text, ["CoStar Group"])
        self.assertEqual(fixed.count("CoStar"), 3)
        self.assertEqual(counts, {"CoStar": 3})

    def test_a_name_that_already_ends_in_apostrophe_s_is_left_alone(self):
        """Stripping and re-appending produced "McDonald's's" nine times."""
        text = "McDonald's sales rose. McDonald's again."
        fixed, counts = repair(text, ["McDonald's"])
        self.assertEqual(fixed, text)
        self.assertNotIn("'s's", fixed)
        self.assertEqual(counts, {})

    def test_a_widened_phrase_never_swallows_a_function_word(self):
        """The widened pass replaced "For Nvidia" with "NVIDIA", losing "For".

        Width span+1 exists to catch names the model split in two. Any
        capitalised sentence-starter adjacent to the name would otherwise be
        absorbed into the replacement and deleted from the transcript.
        """
        text = "For Nvidia, margins. And Nvidia grew. So Nvidia won."
        fixed, counts = repair(text, ["NVIDIA Corporation"])
        self.assertEqual(fixed, text)
        self.assertIn("For Nvidia", fixed)
        self.assertEqual(counts, {})

    def test_trailing_punctuation_in_a_master_name_is_stripped(self):
        """The master stores "Tesla, Inc." -- the comma survives suffix removal.

        Stripping the raw string first is not enough: the comma only becomes
        trailing once "Inc." is popped, so it has to be stripped again after.
        Otherwise "Teslas" is rewritten to "Tesla," comma and all.
        """
        self.assertEqual(core_name("Tesla, Inc."), "Tesla")
        for name in ("Tesla,", "Tesla, Inc."):
            fixed, counts = repair("Teslas everywhere.", [name])
            self.assertEqual(fixed, "Tesla everywhere.")
            self.assertEqual(counts, {"Tesla": 1})

    def test_quarantined_securities_are_not_usable_names(self):
        """5,545 master rows are quarantined, 1,125 of them all-caps junk.

        THERE / RIGHT / TRUMP / THANK are ticker-shaped strings that were
        harvested and never confirmed. They must not reach a name matcher.
        """
        from whisper_vocab import _securities

        usable = _securities()
        for junk in ("THERE", "RIGHT", "TRUMP", "THANK", "GREAT", "KEVIN", "JAPAN"):
            self.assertNotIn(junk, usable)
        for real in ("NVDA", "AMZN", "FAST", "UNH", "SHW"):
            self.assertIn(real, usable)


class ExpectedNamesTests(unittest.TestCase):
    def test_resolves_from_an_episode_title(self):
        names = expected_names("Fastenal: A Nuts & Bolts Success Story")
        self.assertIn("Fastenal", names)

    def test_resolves_explicit_tickers(self):
        names = expected_names("Portfolio update: $GTX and $TPL")
        self.assertTrue(any("Garrett" in n for n in names))


if __name__ == "__main__":
    unittest.main()
