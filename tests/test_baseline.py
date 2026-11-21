import unittest

from qabro.baseline import has_saved_row


class BaselineEvidenceTests(unittest.TestCase):
    def test_saved_row_requires_exact_unique_accessible_name(self):
        expected = "Baseline sample | 2027-01-20 | operations"
        row = f'    - listitem "{expected}"'
        self.assertTrue(has_saved_row(row, expected))
        self.assertFalse(has_saved_row(f'    - listitem "{expected}-old"', expected))
        self.assertFalse(has_saved_row(f'  - status "{expected}"', expected))
        self.assertFalse(has_saved_row(f"{row}\n{row}", expected))
