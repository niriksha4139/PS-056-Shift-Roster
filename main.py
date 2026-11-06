
import csv
from pathlib import Path
from datetime import date, datetime, timedelta
from collections import defaultdict

BASE_DIR = Path(__file__).resolve().parent

CSV_FILES = [
    "agents.csv",
    "shifts.csv",
    "demand.csv",
    "holidays.csv",
    "prior_week_hours.csv",
    "punches.csv",
]

ROSTER_COLUMNS = [
    "roster_date", "agent_id", "shift_code", "skill", "status"
]

VIOLATION_COLUMNS = [
    "agent_id", "violation_date", "rule_id",
    "detail", "hours_affected"
]

ALLOWANCE_COLUMNS = [
    "agent_id", "regular_hours", "overtime_hours",
    "overtime_pay", "night_shifts", "night_hours_other",
    "night_allowance", "off_days_worked", "off_premium",
    "meal_allowance", "total_allowance"
]

SWAP_COLUMNS = [
    "swap_id", "request_ts", "agent_a", "agent_b",
    "decision", "failing_rule_id"
]


def load_csv(filename):
    with open(BASE_DIR / filename, "r", newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def save_csv(filename, rows, columns):
    with open(BASE_DIR / filename, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)
    print("Saved:", filename)


def load_commands():
    commands = []
    with open(BASE_DIR / "commands.txt", encoding="utf-8-sig") as f:
        for number, line in enumerate(f, start=1):
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split("|")
            commands.append({
                "line": number,
                "name": parts[0],
                "args": parts[1:],
            })
    return commands


def parse_timestamp(value):
    value = value.strip()
    formats = [
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%d-%m-%Y %H:%M:%S",
        "%d-%m-%Y %H:%M",
    ]

    try:
        return datetime.fromisoformat(value)
    except ValueError:
        for fmt in formats:
            try:
                return datetime.strptime(value, fmt)
            except ValueError:
                pass

    raise ValueError("Unknown timestamp: " + value)


def get_quarter_hours(agent):
    return float(agent.get("quarter_ot_hours_to_date", 0) or 0)


def generate_roster(data, month):
    agents = data["agents.csv"]
    demand = data["demand.csv"]

    year, mon = map(int, month.split("-"))
    current = date(year, mon, 1)

    roster = []
    streak = {a["agent_id"]: 0 for a in agents}
    weekdays = ["MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN"]

    while current.year == year and current.month == mon:
        day = current.isoformat()
        weekday = weekdays[current.weekday()]

        daily = {
            a["agent_id"]: {
                "roster_date": day,
                "agent_id": a["agent_id"],
                "shift_code": "OFF",
                "skill": "",
                "status": "OFF",
            }
            for a in agents
        }

        shortfalls = []

        for shift in ["MORNING", "EVENING", "NIGHT"]:
            for skill in ["VOICE", "CHAT", "EMAIL"]:
                required = sum(
                    int(r["required_agents"])
                    for r in demand
                    if r.get("date", r.get("demand_date")) == day
                    and r["shift_code"] == shift
                    and r["skill"] == skill
                )

                assigned = 0

                for a in agents:
                    aid = a["agent_id"]

                    if daily[aid]["shift_code"] != "OFF":
                        continue

                    if a["weekly_off"].strip().upper() == weekday:
                        continue

                    skills = [
                        s.strip().upper()
                        for s in a.get("skills", "").split(";")
                    ]

                    if skill not in skills:
                        continue

                    joined = date.fromisoformat(a["joining_date"])

                    if shift == "NIGHT" and (current - joined).days < 90:
                        continue

                    if streak[aid] >= 6:
                        continue

                    daily[aid] = {
                        "roster_date": day,
                        "agent_id": aid,
                        "shift_code": shift,
                        "skill": skill,
                        "status": "ASSIGNED",
                    }

                    assigned += 1

                    if assigned >= required:
                        break

                if assigned < required:
                    shortfalls.append({
                        "roster_date": day,
                        "agent_id": "",
                        "shift_code": shift,
                        "skill": skill,
                        "status": f"SHORTFALL:{required - assigned}",
                    })

        for a in agents:
            aid = a["agent_id"]

            if daily[aid]["status"] == "OFF":
                streak[aid] = 0
            else:
                streak[aid] += 1

            roster.append(daily[aid])

        roster.extend(shortfalls)
        current += timedelta(days=1)

    return roster


def process_punches(punches, agents, prior_week_hours, month, roster, shifts):
    seen = set()
    valid = []
    violations = []

    agent_by_id = {a["agent_id"]: a for a in agents}
    shift_map = {s["shift_code"]: s for s in shifts}

    roster_by_key = {
        (r["agent_id"], r["roster_date"]): r["shift_code"]
        for r in roster
        if r["status"] == "ASSIGNED"
    }

    # Track actual punches, including work on days marked OFF.
    for row_num, p in enumerate(punches, start=2):
        key = tuple(p.get(k, "") for k in p)

        if key in seen:
            print("Duplicate punch ignored at CSV row", row_num)
            continue

        seen.add(key)

        try:
            start = parse_timestamp(p["punch_in"])
            end = parse_timestamp(p["punch_out"])

            if end <= start:
                print("Invalid punch ignored at CSV row", row_num)
                continue

            aid = p["agent_id"]
            day = p["shift_date"]

            if aid not in agent_by_id:
                print("Unknown agent ignored at CSV row", row_num)
                continue

            if day != start.date().isoformat():
                print("Punch date mismatch at CSV row", row_num)

            shift_code = roster_by_key.get((aid, day))

            # If no shift was assigned, infer the closest shift from
            # the actual punch-in time instead of discarding the punch.
            if shift_code not in shift_map:
                punch_minutes = start.hour * 60 + start.minute

                def time_distance(shift):
                    shift_start = datetime.strptime(
                        shift["start_time"], "%H:%M"
                    ).time()
                    shift_minutes = shift_start.hour * 60 + shift_start.minute
                    difference = abs(punch_minutes - shift_minutes)
                    return min(difference, 1440 - difference)

                shift_code = min(
                    shift_map,
                    key=lambda code: time_distance(shift_map[code])
                )

                print(
                    "Shift inferred from punch for",
                    aid, day, ":", shift_code
                )

            scheduled_start = datetime.strptime(
                shift_map[shift_code]["start_time"], "%H:%M"
            ).time()

            scheduled_datetime = datetime.combine(
                date.fromisoformat(day), scheduled_start
            )

            late_minutes = (
                start - scheduled_datetime
            ).total_seconds() / 60

            if 0 < late_minutes <= 10:
                start = scheduled_datetime
            elif late_minutes > 10:
                start += timedelta(minutes=15)

            hours = max(
                0.0,
                (end - start).total_seconds() / 3600 - 0.5
            )

            valid.append({
                "agent_id": aid,
                "shift_date": day,
                "start": start,
                "end": end,
                "hours": hours,
                "shift_code": shift_code,
            })

            if hours > 9:
                violations.append({
                    "agent_id": aid,
                    "violation_date": day,
                    "rule_id": "VIOLATION_DAILY",
                    "detail": (
                        f"Worked {hours:.2f} hours; daily limit is 9"
                    ),
                    "hours_affected": f"{hours - 9:.2f}",
                })

        except (ValueError, KeyError) as error:
            print("Punch row", row_num, "rejected:", error)

    valid.sort(key=lambda p: (p["agent_id"], p["start"]))

    weekly_hours = defaultdict(float)

    for previous in prior_week_hours:
        try:
            aid = previous["agent_id"]
            work_day = date.fromisoformat(previous["work_date"])
            week_start = work_day - timedelta(days=work_day.weekday())
            weekly_hours[(aid, week_start)] += float(
                previous.get("worked_hours", 0) or 0
            )
        except (KeyError, ValueError):
            print("Invalid prior-week row ignored:", previous)

    quarter_used = {
        aid: get_quarter_hours(agent)
        for aid, agent in agent_by_id.items()
    }

    monthly_totals = defaultdict(lambda: {
        "regular_hours": 0.0,
        "overtime_hours": 0.0,
        "overtime_pay": 0.0,
        "night_shifts": 0,
        "night_hours_other": 0.0,
        "night_allowance": 0.0,
        "off_days_worked": 0,
        "off_premium": 0.0,
        "meal_allowance": 0.0,
        "total_allowance": 0.0,
    })

    for p in valid:
        aid = p["agent_id"]
        shift_day = date.fromisoformat(p["shift_date"])
        week_start = shift_day - timedelta(days=shift_day.weekday())
        week_key = (aid, week_start)
        month_key = p["shift_date"][:7]

        before = weekly_hours[week_key]
        regular = max(0.0, min(p["hours"], 48.0 - before))
        raw_overtime = p["hours"] - regular

        remaining_cap = max(
            0.0, 125.0 - quarter_used.get(aid, 0.0)
        )
        paid_overtime = min(raw_overtime, remaining_cap)

        weekly_hours[week_key] += p["hours"]
        quarter_used[aid] = quarter_used.get(aid, 0.0) + paid_overtime

        if month_key != month:
            continue

        totals = monthly_totals[(month_key, aid)]
        totals["regular_hours"] += regular
        totals["overtime_hours"] += paid_overtime

        agent = agent_by_id[aid]
        monthly_basic = float(agent.get("monthly_basic", 0) or 0)
        hourly_basic = monthly_basic / 208 if monthly_basic else 0
        daily_basic = monthly_basic / 26 if monthly_basic else 0

        totals["overtime_pay"] += paid_overtime * hourly_basic * 1.5

        # Count work on the agent's weekly off.
        if shift_day.strftime("%a").upper() == agent["weekly_off"].strip().upper():
            totals["off_days_worked"] += 1
            totals["off_premium"] += daily_basic * 2

        # Count time between 22:00 and 06:00 for night allowance.
        night_seconds = 0
        current_time = p["start"]

        while current_time < p["end"]:
            next_time = min(
                current_time + timedelta(minutes=1), p["end"]
            )
            if current_time.hour >= 22 or current_time.hour < 6:
                night_seconds += (next_time - current_time).total_seconds()
            current_time = next_time

        night_hours = night_seconds / 3600
        totals["night_allowance"] += night_hours * 25

        if p["shift_code"] == "NIGHT":
            totals["night_shifts"] += 1
        else:
            totals["night_hours_other"] += night_hours

    for totals in monthly_totals.values():
        totals["total_allowance"] = (
            totals["night_allowance"]
            + totals["off_premium"]
            + totals["meal_allowance"]
        )

    allowance_rows = []

    for (month_key, aid), totals in sorted(monthly_totals.items()):
        row = {"agent_id": aid}
        for col in ALLOWANCE_COLUMNS[1:]:
            row[col] = round(totals.get(col, 0.0), 2)
        allowance_rows.append(row)

    return valid, violations, allowance_rows


def validate_swap(request, roster, agents, shifts):
    agent_map = {a["agent_id"]: a for a in agents}
    shift_map = {s["shift_code"]: s for s in shifts}

    a = request["agent_a"]
    b = request["agent_b"]
    date_a = request["date_a"]
    date_b = request["date_b"]
    shift_a = request["shift_a"]
    shift_b = request["shift_b"]

    if a not in agent_map or b not in agent_map:
        return "REJECTED", "INVALID_AGENT"

    if a == b:
        return "REJECTED", "SAME_AGENT"

    if shift_a not in shift_map:
        return "REJECTED", "INVALID_SHIFT"

    if shift_b != "OFF" and shift_b not in shift_map:
        return "REJECTED", "INVALID_SHIFT"

    try:
        requested_at = parse_timestamp(request["request_ts"])
        date_a_obj = date.fromisoformat(date_a)

        start_a_time = datetime.strptime(
            shift_map[shift_a]["start_time"], "%H:%M"
        ).time()
        start_a = datetime.combine(date_a_obj, start_a_time)
        starts = [start_a]

        if shift_b != "OFF":
            date_b_obj = date.fromisoformat(date_b)
            start_b_time = datetime.strptime(
                shift_map[shift_b]["start_time"], "%H:%M"
            ).time()
            starts.append(datetime.combine(date_b_obj, start_b_time))

        if min(starts) - requested_at < timedelta(hours=24):
            return "REJECTED", "SWAP_NOTICE_LESS_THAN_24_HOURS"

    except (ValueError, KeyError):
        return "REJECTED", "INVALID_DATE_OR_TIME"

    roster_map = {
        (r["agent_id"], r["roster_date"]): r
        for r in roster
        if r.get("status") == "ASSIGNED"
    }

    assignment_a = roster_map.get((a, date_a))
    if not assignment_a or assignment_a["shift_code"] != shift_a:
        return "REJECTED", "SHIFT_MISMATCH"

    assignment_b = None

    if shift_b != "OFF":
        assignment_b = roster_map.get((b, date_b))
        if not assignment_b or assignment_b["shift_code"] != shift_b:
            return "REJECTED", "SHIFT_MISMATCH"

        if assignment_a.get("skill") != assignment_b.get("skill"):
            return "REJECTED", "SKILL_MISMATCH"

    targets = [(a, shift_b, date_a)]
    if shift_b != "OFF":
        targets.append((b, shift_a, date_b))

    for agent_id, target_shift, target_date in targets:
        agent = agent_map[agent_id]

        try:
            joined = date.fromisoformat(agent["joining_date"])
            target_day = date.fromisoformat(target_date)
        except (ValueError, KeyError):
            return "REJECTED", "INVALID_DATE_OR_TIME"

        if target_shift == "NIGHT" and (target_day - joined).days < 90:
            return "REJECTED", "NEW_JOINER_NIGHT_RESTRICTION"

    def shift_interval(day, code):
        shift = shift_map[code]
        start_time = datetime.strptime(
            shift["start_time"], "%H:%M"
        ).time()
        end_time = datetime.strptime(
            shift["end_time"], "%H:%M"
        ).time()

        start = datetime.combine(date.fromisoformat(day), start_time)
        end = datetime.combine(date.fromisoformat(day), end_time)

        if end <= start:
            end += timedelta(days=1)

        return start, end

    proposed = [(a, date_a, shift_b)]
    if shift_b != "OFF":
        proposed.append((b, date_b, shift_a))

    changed_keys = {(a, date_a)}
    if shift_b != "OFF":
        changed_keys.add((b, date_b))

    for agent_id, changed_day, new_shift in proposed:
        if new_shift == "OFF":
            continue

        new_start, new_end = shift_interval(changed_day, new_shift)

        for row in roster:
            if row.get("agent_id") != agent_id:
                continue
            if row.get("status") != "ASSIGNED":
                continue
            if (agent_id, row["roster_date"]) in changed_keys:
                continue

            old_start, old_end = shift_interval(
                row["roster_date"], row["shift_code"]
            )

            if old_end <= new_start:
                gap = (new_start - old_end).total_seconds() / 3600
            elif new_end <= old_start:
                gap = (old_start - new_end).total_seconds() / 3600
            else:
                gap = -1

            if gap < 11:
                return "REJECTED", "REST_GAP"

    return "APPROVED", ""


def main():
    data = {}

    for filename in CSV_FILES:
        data[filename] = load_csv(filename)
        print(filename, "loaded:", len(data[filename]), "records")

    commands = load_commands()
    print("\nTotal commands:", len(commands))

    roster = []
    all_violations = []
    allowance_rows = []
    swap_requests = []
    swap_decisions = []
    approved_per_agent = defaultdict(int)

    for command in commands:
        name = command["name"]
        args = command["args"]

        if name == "GENERATE_ROSTER":
            month = args[0]
            roster = generate_roster(data, month)
            save_csv("roster.csv", roster, ROSTER_COLUMNS)
            save_csv("roster_before_swaps.csv", roster, ROSTER_COLUMNS)
            print("Roster rows:", len(roster))

        elif name == "LOAD_PUNCHES":
            punches = load_csv(args[0])
            month = "2026-09"

            valid, violations, allowance_rows = process_punches(
                punches,
                data["agents.csv"],
                data["prior_week_hours.csv"],
                month,
                roster,
                data["shifts.csv"],
            )

            all_violations.extend(violations)
            print("Valid punch records:", len(valid))
            print("Daily violations found:", len(violations))

        elif name == "SWAP_REQUEST":
            if len(args) != 8:
                print("Invalid SWAP_REQUEST at line", command["line"])
                continue

            (
                request_ts, swap_id, agent_a, date_a, shift_a,
                agent_b, date_b, shift_b
            ) = args

            swap_requests.append({
                "request_ts": request_ts,
                "swap_id": swap_id,
                "agent_a": agent_a,
                "date_a": date_a,
                "shift_a": shift_a,
                "agent_b": agent_b,
                "date_b": date_b,
                "shift_b": shift_b,
            })

        elif name == "PROCESS_SWAPS":
            for request in swap_requests:
                decision, rule = validate_swap(
                    request, roster, data["agents.csv"], data["shifts.csv"]
                )

                involved = [request["agent_a"]]
                if request["shift_b"] != "OFF":
                    involved.append(request["agent_b"])

                if decision == "APPROVED" and any(
                    approved_per_agent[aid] >= 4 for aid in involved
                ):
                    decision, rule = "REJECTED", "MONTHLY_SWAP_LIMIT"

                if decision == "APPROVED":
                    for aid in involved:
                        approved_per_agent[aid] += 1

                    for row in roster:
                        if (
                            row["agent_id"] == request["agent_a"]
                            and row["roster_date"] == request["date_a"]
                        ):
                            row["shift_code"] = request["shift_b"]
                            row["status"] = (
                                "OFF" if request["shift_b"] == "OFF"
                                else "ASSIGNED"
                            )
                            if row["status"] == "OFF":
                                row["skill"] = ""

                    if request["shift_b"] != "OFF":
                        for row in roster:
                            if (
                                row["agent_id"] == request["agent_b"]
                                and row["roster_date"] == request["date_b"]
                            ):
                                row["shift_code"] = request["shift_a"]
                                row["status"] = "ASSIGNED"

                swap_decisions.append({
                    "swap_id": request["swap_id"],
                    "request_ts": request["request_ts"],
                    "agent_a": request["agent_a"],
                    "agent_b": request["agent_b"],
                    "decision": decision,
                    "failing_rule_id": rule,
                })

            save_csv("swap_decisions.csv", swap_decisions, SWAP_COLUMNS)
            save_csv("roster.csv", roster, ROSTER_COLUMNS)
            print("Swap requests processed:", len(swap_decisions))
            swap_requests = []

        elif name == "PRINT_ROSTER":
            month = args[0]
            filtered = [
                row for row in roster
                if row["roster_date"].startswith(month)
            ]
            save_csv("roster.csv", filtered, ROSTER_COLUMNS)

        elif name == "PRINT_VIOLATIONS":
            month = args[0]
            filtered = [
                v for v in all_violations
                if v["violation_date"].startswith(month)
            ]
            filtered.sort(
                key=lambda v: (v["violation_date"], v["agent_id"])
            )
            save_csv("violations.csv", filtered, VIOLATION_COLUMNS)
            print("Violations:", len(filtered))

        elif name == "PRINT_ALLOWANCES":
            save_csv("allowances.csv", allowance_rows, ALLOWANCE_COLUMNS)

    print("\nProcessing completed.")


if __name__ == "__main__":
    main()
