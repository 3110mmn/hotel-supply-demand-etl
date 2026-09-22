import json
import tempfile
import unittest
from pathlib import Path

from scripts.check_update_result import find_blockers, validate_update_result


class UpdateResultTest(unittest.TestCase):
    def test_empty_review_fields_are_accepted(self) -> None:
        payload = {
            "prefecture": {"updated": False, "configuration_required": []},
            "municipality": {"updated": True, "approval_required": []},
        }
        self.assertEqual(find_blockers(payload), [])

    def test_nested_review_requirement_blocks_publication(self) -> None:
        payload = {
            "prefecture": {
                "updated": False,
                "configuration_required": [{"year": 2026}],
            }
        }
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "result.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "configuration_required"):
                validate_update_result(path)


class DeploymentWorkflowTest(unittest.TestCase):
    def test_pages_regenerates_from_latest_successful_database(self) -> None:
        workflow = Path(".github/workflows/pages.yml").read_text(encoding="utf-8")
        restore = workflow.index("actions/cache/restore@v4")
        # These steps must not depend solely on the cache restore above: it
        # can (and did) miss after 7 days of inactivity, so the regenerate
        # step re-fetches from the git-committed source configs itself.
        fetch = workflow.index("hotel-etl fetch")
        build_database = workflow.index("hotel-etl build-db")
        municipality_fetch = workflow.index("hotel-etl municipality-fetch")
        municipality_build = workflow.index("hotel-etl municipality-build-db")
        prefecture_report = workflow.index("hotel-etl monitor")
        municipality_report = workflow.index("hotel-etl municipality-report")
        stage = workflow.index("python3 scripts/prepare_pages.py")
        self.assertLess(restore, fetch)
        self.assertLess(fetch, build_database)
        self.assertLess(build_database, municipality_fetch)
        self.assertLess(municipality_fetch, municipality_build)
        self.assertLess(municipality_build, prefecture_report)
        self.assertLess(prefecture_report, municipality_report)
        self.assertLess(municipality_report, stage)
        self.assertNotIn("test -f data/processed/hotel_market.sqlite3", workflow)

    def test_update_regenerates_both_reports_before_staging(self) -> None:
        workflow = Path(".github/workflows/update-and-deploy.yml").read_text(encoding="utf-8")
        result_gate = workflow.index("scripts/check_update_result.py update-result.json")
        fetch = workflow.index("hotel-etl fetch")
        build_database = workflow.index("hotel-etl build-db")
        municipality_fetch = workflow.index("hotel-etl municipality-fetch")
        municipality_build = workflow.index("hotel-etl municipality-build-db")
        prefecture_report = workflow.index("hotel-etl monitor")
        municipality_report = workflow.index("hotel-etl municipality-report")
        stage = workflow.index("python scripts/prepare_pages.py")
        self.assertLess(result_gate, fetch)
        self.assertLess(fetch, build_database)
        self.assertLess(build_database, municipality_fetch)
        self.assertLess(municipality_fetch, municipality_build)
        self.assertLess(municipality_build, prefecture_report)
        self.assertLess(prefecture_report, municipality_report)
        self.assertLess(municipality_report, stage)


if __name__ == "__main__":
    unittest.main()
