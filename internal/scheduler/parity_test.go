package scheduler

import (
	"encoding/json"
	"fmt"
	"os"
	"strings"
	"testing"
	"time"
)

// TestCronParity locks the Go port to the Python implementation: the
// fixture file records what launcher.scheduler produced for a battery
// of expressions and fixed "now" times (computed in UTC), and this test
// asserts identical results — fire times, error messages, descriptions.
func TestCronParity(t *testing.T) {
	raw, err := os.ReadFile("testdata/cron_fixtures.json")
	if err != nil {
		t.Fatalf("read fixtures: %v", err)
	}
	var rows []struct {
		Cron     string  `json:"cron"`
		Now      string  `json:"now"`
		Next     *string `json:"next"`
		Error    *string `json:"error"`
		Describe string  `json:"describe"`
	}
	dec := json.NewDecoder(strings.NewReader(string(raw)))
	if err := dec.Decode(&rows); err != nil {
		t.Fatalf("decode fixtures: %v", err)
	}
	for _, row := range rows {
		row := row
		t.Run(fmt.Sprintf("%s@%s", row.Cron, row.Now), func(t *testing.T) {
			c, err := ParseCron(row.Cron)
			if row.Error != nil {
				if err == nil {
					t.Fatalf("expected error %q, got none", *row.Error)
				}
				if err.Error() != *row.Error {
					t.Errorf("error mismatch:\n got  %q\n want %q", err.Error(), *row.Error)
				}
				return
			}
			if err != nil {
				t.Fatalf("unexpected parse error: %v", err)
			}
			now, perr := parseFixtureTime(row.Now)
			if perr != nil {
				t.Fatalf("bad fixture now %q: %v", row.Now, perr)
			}
			got, ok := c.NextAfter(now)
			switch {
			case row.Next == nil:
				if ok {
					t.Errorf("expected no next time, got %s", got.Format(fixtureLayout))
				}
			case !ok:
				t.Errorf("expected next %s, got none", *row.Next)
			default:
				if got.Format(fixtureLayout) != *row.Next {
					t.Errorf("next mismatch:\n got  %s\n want %s", got.Format(fixtureLayout), *row.Next)
				}
			}
			if desc := DescribeCron(row.Cron); desc != row.Describe {
				t.Errorf("describe mismatch:\n got  %q\n want %q", desc, row.Describe)
			}
		})
	}
}

const fixtureLayout = "2006-01-02 15:04"

func parseFixtureTime(s string) (time.Time, error) {
	return time.ParseInLocation(fixtureLayout, s, time.Local)
}

func TestMain(m *testing.M) {
	// Fixtures were computed in UTC by the archived Python
	// implementation (frozen snapshot); pin the test process to the same
	// zone so wall-clock comparisons stay deterministic on any machine.
	time.Local = time.UTC
	os.Exit(m.Run())
}
