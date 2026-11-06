
import csv
import unittest
import py_compile
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent


class TestShiftRoster(unittest.TestCase):

    def read_csv(self, filename):
        with open(
            BASE_DIR / filename,
            newline="",
            encoding="utf-8-sig"
        ) as file:
            return list(csv.DictReader(file))

    def test_main_has_valid_python_syntax(self):
        py_compile.compile(
            str(BASE_DIR / "main.py"),
            doraise=True
        )

    def test_required_input_files_exist(self):
        files = [
            "agents.csv",
            "shifts.csv",
            "demand.csv",
            "prior_week_hours.csv",
            "punches.csv",
        ]
        for filename in files:
            with self.subTest(file=filename):
                self.assertTrue(
                    (BASE_DIR / filename).is_file(),
                    f"Missing input file: {filename}"
                )

    def test_input_csv_files_are_readable(self):
        files = [
            "agents.csv",
            "shifts.csv",
            "demand.csv",
            "prior_week_hours.csv",
            "punches.csv",
        ]
        for filename in files:
            with self.subTest(file=filename):
                with open(
                    BASE_DIR / filename,
                    newline="",
                    encoding="utf-8-sig"
                ) as file:
                    self.assertTrue(
                        next(csv.reader(file), None),
                        f"Empty CSV: {filename}"
                    )

    def test_generated_outputs_exist(self):
        files = [
            "roster.csv",
            "violations.csv",
            "swap_decisions.csv",
            "allowances.csv",
        ]
        for filename in files:
            with self.subTest(file=filename):
                self.assertTrue(
                    (BASE_DIR / filename).is_file(),
                    f"Missing output file: {filename}"
                )

    def test_all_output_headers(self):
        expected_headers = {
            "roster.csv": [
                "roster_date", "agent_id", "shift_code",
                "skill", "status"
            ],
            "violations.csv": [
                "agent_id", "violation_date", "rule_id",
                "detail", "hours_affected"
            ],
            "swap_decisions.csv": [
                "swap_id", "request_ts", "agent_a",
                "agent_b", "decision", "failing_rule_id"
            ],
            "allowances.csv": [
                "agent_id", "regular_hours", "overtime_hours",
                "overtime_pay", "night_shifts",
                "night_hours_other", "night_allowance",
                "off_days_worked", "off_premium",
                "meal_allowance", "total_allowance"
            ],
        }

        for filename, expected in expected_headers.items():
            with self.subTest(file=filename):
                with open(
                    BASE_DIR / filename,
                    newline="",
                    encoding="utf-8-sig"
                ) as file:
                    self.assertEqual(
                        next(csv.reader(file), None),
                        expected
                    )

    def test_swap_decisions_are_valid(self):
        rows = self.read_csv("swap_decisions.csv")

        self.assertEqual(len(rows), 20)

        for row in rows:
            with self.subTest(swap=row["swap_id"]):
                self.assertIn(
                    row["decision"],
                    ["APPROVED", "REJECTED"]
                )

                if row["decision"] == "REJECTED":
                    self.assertTrue(row["failing_rule_id"])

    def test_overtime_never_exceeds_quarterly_cap(self):
        agents = {
            row["agent_id"]: float(
                row["quarter_ot_hours_to_date"]
            )
            for row in self.read_csv("agents.csv")
        }

        for row in self.read_csv("allowances.csv"):
            with self.subTest(agent=row["agent_id"]):
                used_before = agents[row["agent_id"]]
                paid = float(row["overtime_hours"])

                self.assertGreaterEqual(paid, 0)
                self.assertLessEqual(
                    used_before + paid,
                    125.0 + 0.01
                )

    def test_weekly_off_premium_for_agt014(self):
        agents = {
            row["agent_id"]: row
            for row in self.read_csv("agents.csv")
        }
        results = {
            row["agent_id"]: row
            for row in self.read_csv("allowances.csv")
        }

        agent = agents["AGT-014"]
        result = results["AGT-014"]
        daily_basic = float(agent["monthly_basic"]) / 26

        self.assertEqual(int(result["off_days_worked"]), 1)
        self.assertAlmostEqual(
            float(result["off_premium"]),
            round(daily_basic * 2, 2),
            places=2
        )

    def test_daily_violation_hours_are_positive(self):
        rows = self.read_csv("violations.csv")

        for row in rows:
            if row["rule_id"] == "VIOLATION_DAILY":
                with self.subTest(agent=row["agent_id"]):
                    self.assertGreater(
                        float(row["hours_affected"]), 0
                    )

    def test_maximum_four_approved_swaps_per_agent(self):
        rows = self.read_csv("swap_decisions.csv")
        approved_count = {}

        for row in rows:
            if row["decision"] == "APPROVED":
                for agent in (row["agent_a"], row["agent_b"]):
                    approved_count[agent] = (
                        approved_count.get(agent, 0) + 1
                    )

        for agent, count in approved_count.items():
            with self.subTest(agent=agent):
                self.assertLessEqual(count, 4)

    def test_swap_ids_are_unique(self):
        rows = self.read_csv("swap_decisions.csv")
        swap_ids = [row["swap_id"] for row in rows]

        self.assertEqual(len(rows), 20)
        self.assertEqual(len(swap_ids), len(set(swap_ids)))


if __name__ == "__main__":
    unittest.main()
