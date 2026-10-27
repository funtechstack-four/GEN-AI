import unittest

from agents.critic import normalized_quote, quote_for
from agents.excerpt import snap_to_words
from agents.sources import serial_notice_quote


def _whole_words(quote: str, source: str) -> bool:
    i = source.find(quote)
    j = i + len(quote)
    return i >= 0 and (i == 0 or source[i - 1].isspace()) and (j == len(source) or source[j].isspace())


class ExcerptTests(unittest.TestCase):
    def test_cut_moves_to_the_nearest_space(self):
        text = "IT IS notified for the general information. ABDI HASSAN ALI, Government Printer."
        self.assertEqual(snap_to_words(text, text.index("ed for"), text.index("ernment")),
                         "for the general information. ABDI HASSAN ALI,")

    def test_a_window_already_on_word_edges_is_unchanged(self):
        text = "one two three four"
        self.assertEqual(snap_to_words(text, 4, 13), "two three")

    def test_whole_text_is_returned_as_is(self):
        self.assertEqual(snap_to_words("short text", 0, 100), "short text")

    def test_parcel_quote_starts_and_ends_on_whole_words(self):
        source = ("is registered as proprietor in absolute ownership interest of all that piece of land "
                  "registered under title No. N/Wanga/Matungu/954, and whereas sufficient evidence has been "
                  "adduced to show that the land title deed issued thereof has been lost, notice is given "
                  "that after the expiration of sixty (60) days from the date hereof, I shall issue a "
                  "replacement title provided that no objection has been received")
        quote = quote_for("N/Wanga/Matungu/954", source)
        self.assertIn("N/Wanga/Matungu/954", quote)
        self.assertTrue(_whole_words(quote, source), quote)

    def test_serial_quote_starts_and_ends_on_whole_words(self):
        import pyarrow.parquet as pq
        from agents import config

        table = pq.read_table(config.ROOT / "data" / "extracts" / "gazette_notices.parquet",
                              columns=["raw_text"], filters=[("notice_id", "=", "2024-09-27:12436")])
        source = str(table.column("raw_text")[0].as_py())
        quote = serial_notice_quote("2024-09-27:12436")
        self.assertIn(normalized_quote(quote), normalized_quote(source))
        self.assertTrue(_whole_words(quote, source), quote[:40] + " ... " + quote[-40:])


if __name__ == "__main__":
    unittest.main()
