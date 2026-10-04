import unittest

from pricemonitor.exceptions import PriceParseError
from pricemonitor.parsing import parse_price


class ParsePriceTests(unittest.TestCase):
    def test_common_formats(self) -> None:
        cases = {
            "£51.77": 51.77,
            "$1,299.00": 1299.00,
            "Rs. 1,299": 1299.0,
            "₹ 12,499.50": 12499.50,
            "12,99 €": 12.99,
            "1.299,00 €": 1299.00,
            "1 299,00 €": 1299.00,
            "1.299.000": 1299000.0,
            "USD 5": 5.0,
            "Now only $19.99 (was $25)": 19.99,
        }
        for text, expected in cases.items():
            with self.subTest(text=text):
                self.assertAlmostEqual(parse_price(text), expected)

    def test_price_followed_by_stock_note_is_not_merged(self) -> None:
        self.assertAlmostEqual(parse_price("£51.77 2 left"), 51.77)

    def test_empty_text_raises(self) -> None:
        for text in ("", "   ", None):
            with self.subTest(text=text):
                with self.assertRaises(PriceParseError):
                    parse_price(text)

    def test_text_without_number_raises(self) -> None:
        with self.assertRaises(PriceParseError):
            parse_price("Out of stock")


if __name__ == "__main__":
    unittest.main()
