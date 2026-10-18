from pathlib import Path
import unittest

from core.parsers import SignalParseError, parse_cell_info, parse_signal_response


FIXTURES = Path(__file__).parent / "fixtures"


class SignalParserTests(unittest.TestCase):
    def test_parses_huawei_shaped_signal_xml_fixture(self):
        response = (FIXTURES / "huawei_device_signal.xml").read_text(encoding="utf-8")
        readings = parse_signal_response(response)

        self.assertEqual(readings["4G LTE"]["RSRP"], "-96 dBm")
        self.assertEqual(readings["4G LTE"]["PCI"], "123")
        self.assertEqual(readings["5G NR"]["RSRP"], "-88 dBm")
        self.assertEqual(readings["5G NR"]["النطاق"], "n78")

    def test_parses_real_library_decoded_field_names_without_inventing_nr(self):
        readings = parse_signal_response({
            "rsrp": "-101dBm",
            "rsrq": "-12dB",
            "sinr": "8dB",
            "cell_id": "998877",
        })

        self.assertEqual(readings["4G LTE"]["RSRP"], "-101 dBm")
        self.assertFalse(readings["5G NR"])

    def test_reports_unknown_signal_xml(self):
        with self.assertRaises(SignalParseError):
            parse_signal_response("<response><state>CONNECTED</state></response>")

    def test_does_not_present_non_numeric_signal_as_a_reading(self):
        with self.assertRaises(SignalParseError):
            parse_signal_response({"rsrp": "CONNECTED"})

    def test_parses_serving_cell_fields(self):
        response = (FIXTURES / "huawei_device_signal.xml").read_text(encoding="utf-8")
        cell = parse_cell_info(response)

        self.assertEqual(cell["معرّف الخلية"], "12345678")
        self.assertEqual(cell["PCI"], "123")


if __name__ == "__main__":
    unittest.main()
