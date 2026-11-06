<<<<<<< HEAD
# PS-056 – Shift Roster and Overtime Engine with Labour-Law Hours and Swaps — Sample Data Pack

Prepared by 10 SECONDS for Team T078.

Domain: Enterprise / HR – Workforce Scheduling. Build the back-end engine a 24x7 BPO uses to generate a monthly shift roster for its agents, enforce statutory working-hour limits, compute overtime and night allowances, and process shift swap requests. Command-file driven; no UI.

## Files

| File | What it holds | Rows |
|---|---|---|
| `agents.csv` | Agents | 30 |
| `shifts.csv` | Shift templates | 3 |
| `demand.csv` | Daily demand per shift per skill for 2026-09 | 270 |
| `holidays.csv` | Public holidays (informational; BPO runs 24x7) | 2 |
| `prior_week_hours.csv` | Hours already worked on Mon 2026-08-31 (the week that spans the month boundary) | 30 |
| `punches.csv` | Actual punches (one row per worked shift; missing row = absent) | 659 |
| `commands.txt` | Command file; process strictly in file order. | 26 |

Row counts exclude the header line (CSV) and comment lines (commands.txt).

## Column reference

Conventions: dates `YYYY-MM-DD`; timestamps `YYYY-MM-DD HH:MM:SS` (24h, IST, no timezone suffix); money in Rs as plain decimals with at most 2 decimals (no commas, no symbol); percentages as plain numbers (12.5 = 12.5%); booleans `true`/`false`; IDs uppercase with a fixed prefix.

### `agents.csv`

| Column | Type | Units / format | Allowed values | Notes |
|---|---|---|---|---|
| `agent_id` | string | AGT-nnn |  | Primary key; tie-break order |
| `name` | string |  |  |  |
| `gender` | enum |  | M/F |  |
| `grade` | enum |  | A1/A2/A3 |  |
| `skills` | list | semicolon-separated | VOICE/CHAT/EMAIL |  |
| `weekly_off` | enum |  | MON..SUN | The scheduled weekly off day (one per Mon–Sun week) |
| `joining_date` | date |  |  | Agents joined < 90 days before the shift date may not work NIGHT |
| `monthly_basic` | decimal | Rs |  | hourly basic = monthly_basic / 208; daily basic = monthly_basic / 26 |
| `quarter_ot_hours_to_date` | decimal | hours | 0–125 | Overtime already worked in Jul–Aug 2026 (quarter cap 125) |

### `shifts.csv`

| Column | Type | Units / format | Allowed values | Notes |
|---|---|---|---|---|
| `shift_code` | enum |  | MORNING/EVENING/NIGHT |  |
| `start_time` | time | HH:MM |  |  |
| `end_time` | time | HH:MM |  | NIGHT ends next day |
| `paid_hours` | decimal | hours |  | 8 h span minus 30 min unpaid break |
| `unpaid_break_minutes` | integer | minutes |  |  |

### `demand.csv`

| Column | Type | Units / format | Allowed values | Notes |
|---|---|---|---|---|
| `demand_date` | date |  |  |  |
| `shift_code` | enum |  |  |  |
| `skill` | enum |  |  |  |
| `required_agents` | integer |  | >=0 |  |

### `holidays.csv`

| Column | Type | Units / format | Allowed values | Notes |
|---|---|---|---|---|
| `holiday_date` | date |  |  |  |
| `name` | string |  |  |  |

### `prior_week_hours.csv`

| Column | Type | Units / format | Allowed values | Notes |
|---|---|---|---|---|
| `agent_id` | string |  | agents.csv | FK |
| `work_date` | date |  | 2026-08-31 |  |
| `shift_code` | enum |  | MORNING/EVENING/NIGHT/OFF |  |
| `worked_hours` | decimal | hours |  |  |
| `overtime_hours` | decimal | hours |  |  |

### `punches.csv`

| Column | Type | Units / format | Allowed values | Notes |
|---|---|---|---|---|
| `agent_id` | string |  | agents.csv | FK |
| `shift_date` | date |  |  | The rostered shift date (NIGHT punches out next day) |
| `punch_in` | timestamp |  |  |  |
| `punch_out` | timestamp |  |  | Worked hours = span minus the 30-minute unpaid break |

### General notes

- Where the brief is silent: worked hours = punch span minus the 30-minute unpaid break; overtime is computed on worked hours above 48 in a Mon–Sun week; the roster fill order is MORNING, EVENING, NIGHT then skills VOICE, CHAT, EMAIL within each day.

## Command file format

`commands.txt` holds one command per line in the form `COMMAND_NAME|arg1|arg2|...`. Commands MUST be processed strictly in file order. Lines starting with `#` are comments and blank lines are ignored. Every command used in this pack, with its argument order:

| Command | Arguments (in order) | Meaning |
|---|---|---|
| `GENERATE_ROSTER` | `YYYY-MM` | Build the month's roster from demand.csv using the fill rules |
| `LOAD_PUNCHES` | `file` | Load actual punches and compute worked/OT/night hours and violations |
| `SWAP_REQUEST` | `request_ts|swap_id|agent_a|date_a|shift_a|agent_b|date_b or -|shift_b or OFF` | Agent A gives shift_a on date_a to B and takes shift_b on date_b (OFF = shift-for-off) |
| `PROCESS_SWAPS` | `` | Validate all swap requests in file order against the roster and punches |
| `PRINT_ROSTER` | `YYYY-MM` | Write roster.csv |
| `PRINT_VIOLATIONS` | `YYYY-MM` | Write violations.csv |
| `PRINT_ALLOWANCES` | `YYYY-MM` | Write allowances.csv |

## Planted scenarios

Every edge case from the brief is planted at the location given. Line numbers count the header as line 1 for CSVs and count every physical line (including comments) for commands.txt.

- **EC1: Worked 9 hours exactly versus 9 hours 1 minute on a day** — punches.csv line 23: AGT-009 MORNING punch span 9 h 30 min → worked 9.00 h exactly (no violation); punches.csv line 43: AGT-010 span 9 h 31 min → 9 h 01 min → VIOLATION_DAILY, paid up to 9
- **EC2: Week with 48.0 hours exactly (no overtime) and week where the 48th hour ends mid-shift** — AGT-001 week Mon 2026-09-07 to Sat 2026-09-12: six punches of 8 h 30 min span (from punches.csv line 132) → 6 x 8.00 = 48.0 h, no overtime; AGT-002 same week: Mon–Fri 9.00 h each (from punches.csv line 133) = 45 h, then Saturday (punches.csv line 250) 7.5 h → the 48th hour ends 3 h into Saturday's shift, remaining 4.5 h are overtime
- **EC3: Overtime that crosses 22:00 by 30 minutes on an EVENING shift** — punches.csv line 14: AGT-011 EVENING shift punched out at 22:30:00 → 30 minutes past 22:00 → night allowance Rs 25 x 0.5 = 12.50 on a non-NIGHT shift
- **EC4: Agent reaching 125 quarterly overtime hours mid-shift** — agents.csv AGT-026 quarter_ot_hours_to_date 124.50; week 2026-09-07..12 it works 9.00 h daily (from punches.csv line 134) → the first 0.5 h of overtime reaches 125 mid-shift; later overtime must not be paid/assigned
- **EC5: NIGHT shift ending at 06:00 followed by EVENING shift at 14:00 (8-hour gap, breach)** — commands.txt line 4: SWAP_REQUEST where an agent rostered NIGHT (ends 06:00) would take an EVENING shift starting 14:00 the next day → 8-hour rest gap → REJECTED with the rest-gap rule id
- **EC6: Six consecutive working days that span the end of one week and the start of the next** — AGT-004 has weekly_off WED: under the fill rules it is rostered Thu 2026-09-03 … Tue 2026-09-08 = 6 consecutive working days spanning the Sun/Mon week boundary (allowed, the 7th would not be)
- **EC7: Swap requested exactly 24 hours before the shift** — commands.txt line 5: request timestamp exactly 24 h before the earlier shift start → allowed; commands.txt line 6: 23 h 59 min before → REJECTED (late request)
- **EC8: Month boundary falling mid-week: weekly limit evaluation spanning two months** — prior_week_hours.csv gives each agent's Mon 2026-08-31 hours; the Mon–Sun week 2026-08-31..2026-09-06 must be evaluated with those hours included; the month ends Wed 2026-09-30 mid-week (week 2026-09-28..10-04 is partial)
- **Extra: punch tolerance boundary** — punches.csv line 326: AGT-012 punches in 10 minutes late → snaps to schedule; punches.csv line 313: AGT-013 11 minutes late → one 15-minute block deducted
- **Extra: worked on weekly off** — punches.csv line 267: AGT-014 punches a MORNING shift on its weekly off → 1.0 x daily basic premium, compensatory off needed within 14 days (none given → premium doubles)
- **Extra: new joiner and NIGHT** — AGT-025 joined 2026-07-15 (< 90 days) → never rostered on NIGHT; commands.txt line 7 asks AGT-025 to take a NIGHT shift → REJECTED
- **Extra: swap skill mismatch** — commands.txt line 8: AGT-005 (EMAIL only) asked to take a VOICE MORNING shift → REJECTED skill rule
- **Extra: swap monthly limit** — AGT-003 files 5 swap requests (commands.txt line 15 … commands.txt line 19); the 5th approved-eligible one must be REJECTED (max 4 approved swaps per month)
- **Extra: bad punch rows** — punches.csv line 28 duplicates an earlier row → count once; punches.csv line 429: punch_out before punch_in → reject row, treat as absent
- **Extra: shortfall** — demand.csv 2026-09-17 MORNING requires 7 agents per skill → SHORTFALL rows expected in the roster output

## What is NOT in this pack

Expected outputs are not provided for this set. Validate your engine with your own test suite against the rules in your brief (BR-01 … BR-nn). A separate hidden input set with the same schema will be used at final evaluation; outputs are compared field-for-field, so follow the column formats above exactly in your own output.

## Output format expected at evaluation

Produce these files (CSV, header row, same conventions as above, rows in the order stated). Numeric columns must be plain decimals with exactly the decimals stated.

### `roster.csv`

One row per agent per day, ordered by date then agent_id; SHORTFALL rows at the end of each date.

Columns in order: `roster_date`, `agent_id`, `shift_code`, `skill`, `status`

### `violations.csv`

Every rule breach in date order.

Columns in order: `agent_id`, `violation_date`, `rule_id`, `detail`, `hours_affected`

### `swap_decisions.csv`

One row per SWAP_REQUEST in file order.

Columns in order: `swap_id`, `request_ts`, `agent_a`, `agent_b`, `decision`, `failing_rule_id`

### `allowances.csv`

One row per agent for the month.

Columns in order: `agent_id`, `regular_hours`, `overtime_hours`, `overtime_pay`, `night_shifts`, `night_hours_other`, `night_allowance`, `off_days_worked`, `off_premium`, `meal_allowance`, `total_allowance`
=======
# PS-056-Shift-Roster
Shift Roster and Overtime Engine
>>>>>>> dd570c799daec68418ef8eb60140bfe15c6c7ebd
