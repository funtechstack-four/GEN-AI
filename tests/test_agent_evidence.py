"""Focused guardrail evaluations for the agent's evidence boundary."""
from __future__ import annotations

import unittest

from agents.classifier import classify
from agents.critic import critic_claim, quote_for
from agents.sources import sample_serial, serial_notice_quote


class EvidenceBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.text = (
            "The land parcel registered under title No. N/Wanga/Matungu/954, and whereas "
            "sufficient evidence has been adduced to show that the land title deed issued thereof has been lost."
        )
        self.row = {
            "notice_id": "2024-10-04:12679",
            "parcel_refs": ["N/Wanga/Matungu/954"],
            "raw_text": self.text,
        }

    def claim(self, parcel="N/Wanga/Matungu/954", quote=None):
        return {"quote": quote if quote is not None else quote_for(parcel, self.text)}

    def test_exact_parcel_and_verbatim_quote_are_accepted(self):
        self.assertEqual(critic_claim("N/Wanga/Matungu/954", self.row, self.claim()), (True, ""))

    def test_adjacent_parcel_is_never_confirmed_from_neighbor_evidence(self):
        ok, reason = critic_claim("N/Wanga/Matungu/955", self.row, self.claim("N/Wanga/Matungu/955"))
        self.assertFalse(ok)
        self.assertIn("exact parcel", reason)

    def test_paraphrase_is_rejected_even_when_parcel_matches(self):
        ok, reason = critic_claim("N/Wanga/Matungu/954", self.row, self.claim(quote="This title was reported lost"))
        self.assertFalse(ok)
        self.assertIn("verbatim", reason)

    def test_succession_classification_precedes_generic_transfer(self):
        self.assertEqual(classify({"notice_type": "transfer", "raw_text": "Succession Cause E102 grant of letters of administration"}), "succession")

    def test_preclassified_lost_title_notice_kind_is_preserved(self):
        self.assertEqual(classify({"notice_type": "lost_title", "notice_title": "Issue of a new land title deed"}), "lost_title")

    def test_cancelled_serial_accepts_labelled_and_formatted_input(self):
        row = sample_serial("No. 5,253,012")
        self.assertIsNotNone(row)
        self.assertEqual(row["serial"], "5253012")

    def test_cancelled_serial_excerpt_is_from_the_gazette_source(self):
        quote = serial_notice_quote("2024-09-27:12436")
        self.assertIn("5253001", quote)
        self.assertIn("5253367", quote)
        self.assertIn("deemed cancelled", quote)


if __name__ == "__main__":
    unittest.main()
