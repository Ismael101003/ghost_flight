import unittest
from app import classify_flight


class TestClassifyFlight(unittest.TestCase):
    def test_known_cargo_prefix(self):
        self.assertEqual(classify_flight("FDX123"), "carga")
        self.assertEqual(classify_flight("UPS987"), "carga")
        self.assertEqual(classify_flight("dhl001"), "carga")

    def test_commercial_default(self):
        self.assertEqual(classify_flight("AAL100"), "comercial")
        self.assertEqual(classify_flight("AMX200"), "carga")

    def test_empty_and_none(self):
        self.assertEqual(classify_flight("") , "desconocido")
        self.assertEqual(classify_flight(None) , "desconocido")

    def test_unknown_prefix(self):
        # Unknown prefixes default to comercial in our heuristic
        self.assertEqual(classify_flight("ZZZ123"), "comercial")


if __name__ == '__main__':
    unittest.main()
