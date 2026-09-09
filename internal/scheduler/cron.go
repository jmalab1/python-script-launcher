// Package scheduler is the cron-like scheduling engine for profiles and
// workflows, ported line-for-line from the Python launcher.scheduler so
// behaviour (and the UI's cron previews) stay identical.
//
// Expressions use the standard 5-field cron form:
//
//	minute hour day-of-month month day-of-week
//
// Fields support "*", lists ("a,b"), ranges ("a-b") and steps ("*/n",
// "a-b/n", "a/n"). Day-of-week is 0=Sunday..6=Saturday with 7 accepted
// as Sunday. As in classic cron, when both day-of-month and
// day-of-week are restricted, a day matches if either field matches.
package scheduler

import (
	"fmt"
	"sort"
	"strconv"
	"strings"
	"time"
)

// FieldRanges are the valid bounds per field. DOW accepts 7 and
// normalizes it to 0 (Sunday).
var fieldRanges = map[string][2]int{
	"minute": {0, 59},
	"hour":   {0, 23},
	"dom":    {1, 31},
	"month":  {1, 12},
	"dow":    {0, 7},
}

var fieldOrder = []string{"minute", "hour", "dom", "month", "dow"}

// maxScanDays bounds the next-run day scan; it covers leap years and
// rejects impossible expressions (e.g. "0 0 31 2 *") with a clean
// not-found instead of looping forever.
const maxScanDays = 5*366 + 2

var dayNames = []string{
	"Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday",
}

// Cron holds the parsed value sets of a 5-field cron expression.
type Cron struct {
	Minute, Hour, Dom, Month, Dow map[int]bool

	// DomWild/DowWild/MonthWild are precomputed "is *?" flags.
	DomWild, DowWild, MonthWild bool
}

// ParseCron parses a 5-field cron expression. Errors carry the same
// human-readable messages the Python implementation produced, because
// they are surfaced in the schedule editor.
func ParseCron(expr string) (*Cron, error) {
	if strings.TrimSpace(expr) == "" {
		return nil, fmt.Errorf("cron expression must be a non-empty string")
	}
	fields := strings.Fields(expr)
	if len(fields) != 5 {
		return nil, fmt.Errorf("cron expression must have 5 fields, got %d", len(fields))
	}

	c := &Cron{}
	parts := map[string]*map[int]bool{
		"minute": &c.Minute,
		"hour":   &c.Hour,
		"dom":    &c.Dom,
		"month":  &c.Month,
		"dow":    &c.Dow,
	}

	for i, name := range fieldOrder {
		values, err := parseField(fields[i], name)
		if err != nil {
			return nil, err
		}
		*parts[name] = values
	}

	c.DomWild = isFullRange(c.Dom, 1, 31)
	c.DowWild = isFullRange(c.Dow, 0, 6)
	c.MonthWild = isFullRange(c.Month, 1, 12)
	return c, nil
}

func isFullRange(set map[int]bool, lo, hi int) bool {
	for v := lo; v <= hi; v++ {
		if !set[v] {
			return false
		}
	}
	return true
}

// parseInt mirrors Python's int() for this purpose: optional sign and
// digits, leading zeros allowed ("05" is 5). Any other shape is the
// "invalid number" error, whose text matches the Python message because
// it is surfaced in the schedule editor.
func parseInt(token, field string) (int, error) {
	n, err := strconv.Atoi(token)
	if err != nil {
		return 0, fmt.Errorf("invalid number '%s' in %s field", token, field)
	}
	return n, nil
}

func parseField(token, field string) (map[int]bool, error) {
	lo, hi := fieldRanges[field][0], fieldRanges[field][1]
	values := map[int]bool{}
	for _, part := range strings.Split(token, ",") {
		if part == "" {
			return nil, fmt.Errorf("empty list item in %s field", field)
		}
		step := 1
		rangePart := part
		if strings.Contains(part, "/") {
			idx := strings.Index(part, "/")
			rangePart, step = part[:idx], 0
			stepText := part[idx+1:]
			var err error
			step, err = parseInt(stepText, field)
			if err != nil {
				return nil, err
			}
			if step < 1 {
				return nil, fmt.Errorf("step must be >= 1 in %s field", field)
			}
		}
		var start, end int
		switch {
		case rangePart == "*":
			start, end = lo, hi
		case strings.Contains(rangePart, "-"):
			idx := strings.Index(rangePart, "-")
			var err error
			start, err = parseInt(rangePart[:idx], field)
			if err != nil {
				return nil, err
			}
			end, err = parseInt(rangePart[idx+1:], field)
			if err != nil {
				return nil, err
			}
		default:
			var err error
			start, err = parseInt(rangePart, field)
			if err != nil {
				return nil, err
			}
			if strings.Contains(part, "/") {
				end = hi
			} else {
				end = start
			}
		}
		if start < lo || end > hi || start > end {
			return nil, fmt.Errorf("value '%s' out of range for %s field", rangePart, field)
		}
		if step > hi-lo {
			return nil, fmt.Errorf("step %d too large for %s field", step, field)
		}
		for v := start; v <= end; v += step {
			values[v] = true
		}
	}

	if len(values) == 0 {
		return nil, fmt.Errorf("%s field matches no values", field)
	}

	if field == "dow" && values[7] {
		delete(values, 7)
		values[0] = true
	}
	return values, nil
}

// cronDOW returns the cron day-of-week (0=Sunday) for a time.
// Go's Weekday() is already Sunday=0, matching cron directly.
func cronDOW(t time.Time) int {
	return int(t.Weekday())
}

// dayMatches implements the classic cron rule: when both day-of-month
// and day-of-week are restricted, a day matches if either matches.
func (c *Cron) dayMatches(t time.Time) bool {
	switch {
	case c.DomWild && c.DowWild:
		return true
	case c.DomWild:
		return c.Dow[cronDOW(t)]
	case c.DowWild:
		return c.Dom[t.Day()]
	default:
		return c.Dom[t.Day()] || c.Dow[cronDOW(t)]
	}
}

// NextAfter returns the next fire time strictly after `now`, in local
// wall-clock time, or nil when the expression can never fire.
func (c *Cron) NextAfter(now time.Time) (time.Time, bool) {
	// Zero seconds, then step one minute forward IN WALL-CLOCK terms —
	// the same "strictly after now, minute granularity" rule as the
	// Python code, which adds a timedelta to a naive (DST-unaware)
	// datetime. time.Time.Add would follow the absolute timeline and
	// jump an hour across DST transitions.
	t := time.Date(now.Year(), now.Month(), now.Day(), now.Hour(), now.Minute()+1, 0, 0, time.Local)

	minutes := sortedKeys(c.Minute)
	hours := sortedKeys(c.Hour)

	date := t
	for i := 0; i < maxScanDays; i++ {
		if c.Month[int(date.Month())] && c.dayMatches(date) {
			dayStart := time.Date(date.Year(), date.Month(), date.Day(), 0, 0, 0, 0, time.Local)
			if sameYMD(date, t) {
				for _, h := range hours {
					if h < t.Hour() {
						continue
					}
					if h == t.Hour() {
						for _, m := range minutes {
							if m >= t.Minute() {
								return at(dayStart, h, m), true
							}
						}
					} else {
						return at(dayStart, h, minutes[0]), true
					}
				}
			} else {
				return at(dayStart, hours[0], minutes[0]), true
			}
		}
		date = time.Date(date.Year(), date.Month(), date.Day()+1, 0, 0, 0, 0, time.Local)
	}
	return time.Time{}, false
}

func sameYMD(a, b time.Time) bool {
	return a.Year() == b.Year() && a.Month() == b.Month() && a.Day() == b.Day()
}

func at(dayStart time.Time, hour, minute int) time.Time {
	return time.Date(dayStart.Year(), dayStart.Month(), dayStart.Day(), hour, minute, 0, 0, time.Local)
}

func sortedKeys(set map[int]bool) []int {
	out := make([]int, 0, len(set))
	for v := range set {
		out = append(out, v)
	}
	sort.Ints(out)
	return out
}

// DescribeCron returns a human-readable description of a cron
// expression, or the raw text when it does not match a known pattern.
// Ported exactly from the Python describe_cron so the schedule editor
// shows identical labels.
func DescribeCron(expr string) string {
	c, err := ParseCron(expr)
	if err != nil {
		return expr
	}

	minute, hour := c.Minute, c.Hour
	dom, dow := c.Dom, c.Dow

	if !c.MonthWild {
		return expr
	}

	minuteSorted := sortedKeys(minute)
	hourSorted := sortedKeys(hour)

	if isFullRange(minute, 0, 59) && isFullRange(hour, 0, 23) {
		return "Every minute"
	}
	if len(minuteSorted) > 1 {
		step := minuteSorted[1] - minuteSorted[0]
		if step > 1 && isStepRange(minute, 0, 59, step) && isFullRange(hour, 0, 23) {
			return fmt.Sprintf("Every %d minutes", step)
		}
	}
	if isFullRange(hour, 0, 23) {
		if minuteSorted[0] == 0 && len(minute) == 1 {
			return "Every hour"
		}
		if len(minute) == 1 {
			return fmt.Sprintf("Every hour at :%02d", minuteSorted[0])
		}
	}
	if len(minuteSorted) == 1 && len(hourSorted) > 1 {
		step := hourSorted[1] - hourSorted[0]
		if step > 1 && isStepRange(hour, 0, 23, step) {
			m := minuteSorted[0]
			if m == 0 {
				return fmt.Sprintf("Every %d hours", step)
			}
			return fmt.Sprintf("Every %d hours at :%02d", step, m)
		}
	}
	if len(minute) == 1 && len(hour) == 1 {
		m, h := minuteSorted[0], hourSorted[0]
		timeText := fmt.Sprintf("%02d:%02d", h, m)
		if c.DomWild && c.DowWild {
			return fmt.Sprintf("Daily at %s", timeText)
		}
		if c.DomWild && !c.DowWild {
			days := sortedKeys(dow)
			if eqInts(days, []int{1, 2, 3, 4, 5}) {
				return fmt.Sprintf("Weekdays at %s", timeText)
			}
			var names []string
			for _, d := range days {
				name := dayNames[d]
				if len(days) > 1 {
					name += "s"
				}
				names = append(names, name)
			}
			if len(names) == 1 {
				return fmt.Sprintf("Weekly on %s at %s", names[0], timeText)
			}
			return fmt.Sprintf("%s at %s", strings.Join(names, " & "), timeText)
		}
		if c.DowWild && len(dom) == 1 {
			return fmt.Sprintf("Monthly on day %d at %s", sortedKeys(dom)[0], timeText)
		}
	}
	if c.DowWild && len(dom) > 1 {
		domSorted := sortedKeys(dom)
		step := domSorted[1] - domSorted[0]
		if step > 1 && isStepRange(dom, 1, 31, step) && len(minuteSorted) == 1 && len(hourSorted) == 1 {
			m, h := minuteSorted[0], hourSorted[0]
			suffix := ""
			if !(m == 0 && h == 0) {
				suffix = fmt.Sprintf(" at %02d:%02d", h, m)
			}
			return fmt.Sprintf("Every %d days%s", step, suffix)
		}
	}
	return expr
}

// isStepRange reports whether set is exactly lo, lo+step, ..., hi. The
// Python code used `set(range(lo, hi+1, step)) == set`; a set like
// {5, 35} with step 30 and hi 59 must NOT match, which the length check
// enforces.
func isStepRange(set map[int]bool, lo, hi, step int) bool {
	expected := 0
	for v := lo; v <= hi; v += step {
		if !set[v] {
			return false
		}
		expected++
	}
	return len(set) == expected
}

func eqInts(a, b []int) bool {
	if len(a) != len(b) {
		return false
	}
	for i := range a {
		if a[i] != b[i] {
			return false
		}
	}
	return true
}
