import unittest

from qabro.observation_filter import FilteredObservation, filter_observations


class ObservationFilterTests(unittest.TestCase):
    allowed = {"Save", "Cancel"}

    def test_releases_structure_and_exact_approved_labels(self):
        result = filter_observations([
            {"role": "button", "label": "Save", "state": {"disabled": False}},
            {"role": "button", "label": "Save private record"},
            {"role": "textbox"},
        ], allowed_labels=self.allowed)

        self.assertEqual(result, FilteredObservation("ok", (
            {"role": "button", "label": "Save", "state": {"disabled": False}},
            {"role": "button", "label": None, "state": {}},
            {"role": "textbox", "label": None, "state": {}},
        )))

    def test_fails_closed_without_echoing_out_of_scope_content(self):
        for entry in (
            {"role": "private row role"},
            {"role": "textbox", "value": "private record"},
            {"role": "checkbox", "state": {"private state name": True}},
        ):
            with self.subTest(entry=entry):
                result = filter_observations([
                    {"role": "button", "label": "Save"}, entry,
                ], allowed_labels=self.allowed)
                self.assertEqual(result, FilteredObservation("out_of_scope"))

    def test_releases_visible_table_structure_and_approved_dialog_heading(self):
        result = filter_observations([
            {"role": "table", "label": "private caption", "state": {"visible": True}},
            {"role": "heading", "label": "Create record", "state": {"visible": True, "in_dialog": True}},
        ], allowed_labels={"Create record"})
        self.assertEqual(result, FilteredObservation("ok", (
            {"role": "table", "label": None, "state": {"visible": True}},
            {"role": "heading", "label": "Create record", "state": {"visible": True, "in_dialog": True}},
        )))

    def test_rejects_malformed_shapes(self):
        for payload in (
            {"role": "button"},
            [None],
            [{"role": "button", "label": {"secret": "data"}}],
            [{"role": "button", "state": {"disabled": "true"}}],
            [{"role": "button", "state": {"disabled": 1}}],
        ):
            with self.subTest(payload=payload):
                self.assertEqual(
                    filter_observations(payload, allowed_labels=self.allowed),
                    FilteredObservation("malformed"),
                )

    def test_rejects_unbounded_observations(self):
        self.assertEqual(
            filter_observations([{"role": "button"}] * 129, allowed_labels=self.allowed),
            FilteredObservation("out_of_scope"),
        )
