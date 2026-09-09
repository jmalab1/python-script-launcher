// Package runner executes user scripts and workflows, ported from the
// Python launcher.runner so behaviour matches exactly: line-by-line
// output capture, per-profile timeouts, cancellation, parallel workflow
// steps, and the prunable registry of active runs the run panel polls.
package runner

import (
	"bufio"
	"encoding/json"
	"fmt"
	"os"
	"os/exec"
	"strconv"
	"strings"
	"sync"
	"time"

	"launchcontrol/internal/ordjson"
	"launchcontrol/internal/store"
)

const (
	// CancelMessage is appended to a run's output when the user stops it.
	CancelMessage = "Cancelled by user.\n"

	// DefaultDateFormat is the date field's input format.
	DefaultDateFormat = "2006-01-02"

	// Finished runs stay pollable for this grace period (the run panel
	// falls back to history for anything older), and their total count is
	// capped so the registry cannot grow without bound on a long-lived
	// server.
	FinishedRunTTLSeconds = 600
	MaxFinishedRuns       = 50
)

// finishedStatuses are the states a run ends in; all of them age out of
// the registry the same way (a cancelled run has finished just like a
// completed one).
var finishedStatuses = map[string]bool{
	"completed": true, "failed": true, "cancelled": true,
}

// PythonResolver returns the interpreter used to run user scripts: the
// bundled runtime when available, falling back to a system python3.
type PythonResolver func() (string, error)

// Step is one workflow step's live state. It is marshalled into the
// poll/history JSON shapes the frontend expects.
type Step struct {
	Output     []string
	Status     string
	ReturnCode *int
	Num        int
	Command    []string // set when the step actually started
}

// Run is the live state of one run, the equivalent of the Python
// active_runs entry.
type Run struct {
	ID           string
	Output       []string
	WorkflowLog  []string
	Status       string
	ReturnCode   *int
	Failed       bool
	TimedOut     bool
	Cancelled    bool
	FinishedAt   float64
	StepCount    int
	CurrentStep  string
	Command      []string
	Trigger      string
	ScheduleID   string
	ScheduleName string
	Steps        *ordjson.OMap // display name -> *Step-shaped OMap

	// procs holds the live child processes so cancellation can reach
	// every script of a parallel workflow group.
	procs []*exec.Cmd
}

// Manager owns the active runs registry and starts runs.
type Manager struct {
	db     *store.DB
	Python PythonResolver

	mu      sync.Mutex
	runs    map[string]*Run
	counter int
}

// NewManager creates a runner bound to the database.
func NewManager(db *store.DB, python PythonResolver) *Manager {
	if python == nil {
		python = func() (string, error) { return "python3", nil }
	}
	return &Manager{db: db, Python: python, runs: map[string]*Run{}}
}

// BuildCommand returns the full argv used to launch a script, for
// history and logging.
func (m *Manager) BuildCommand(scriptPath string, args []string) []string {
	exe, err := m.Python()
	if err != nil {
		exe = "python3"
	}
	cmd := []string{exe, scriptPath}
	return append(cmd, args...)
}

// ParseTimeout turns a profile's timeout setting into seconds; zero
// means "no time limit". Numbers or numeric strings are accepted;
// anything missing, unparseable or not positive disables the limit.
func ParseTimeout(value any) float64 {
	switch v := value.(type) {
	case json.Number:
		f, err := v.Float64()
		if err != nil {
			return 0
		}
		if f > 0 {
			return f
		}
		return 0
	case float64:
		if v > 0 {
			return v
		}
		return 0
	case string:
		f, err := strconv.ParseFloat(strings.TrimSpace(v), 64)
		if err != nil {
			return 0
		}
		if f > 0 {
			return f
		}
		return 0
	default:
		return 0
	}
}

// FormatDateValue reformats a YYYY-MM-DD input into the field's format.
// Formats use strftime codes ("%d/%m/%Y"), so they are translated to Go
// layouts first; unknown codes pass through unchanged. Invalid input
// values also pass through.
func FormatDateValue(value, layout string) string {
	if layout == "" || layout == DefaultDateFormat {
		layout = DefaultDateFormat
	}
	t, err := time.Parse(DefaultDateFormat, value)
	if err != nil {
		return value
	}
	return t.Format(strftimeToGo(layout))
}

// strftimeToGo converts the strftime directives the date fields accept
// into Go time layouts.
func strftimeToGo(layout string) string {
	replacements := []string{
		"%Y", "2006", "%y", "06",
		"%m", "01", "%d", "02",
		"%H", "15", "%I", "03",
		"%M", "04", "%S", "05",
		"%B", "January", "%b", "Jan",
		"%A", "Monday", "%a", "Mon",
		"%p", "PM",
		"%%", "%",
	}
	out := strings.NewReplacer(replacements...).Replace(layout)
	// A trailing lone "%" would confuse time.Format; keep it literal.
	return strings.Replace(out, "%", "%%", strings.Count(out, "%")-strings.Count(out, "%%"))
}

// BuildCustomArgs turns a profile's custom argument fields into CLI
// arguments. Values from argValues (the card's current inputs or a
// workflow step's overrides) take precedence over stored values.
func BuildCustomArgs(customArgs []any, argValues *ordjson.OMap) []string {
	var overrides *ordjson.OMap
	if argValues != nil {
		overrides = argValues
	}
	built := []string{}
	for _, raw := range customArgs {
		ca, ok := raw.(*ordjson.OMap)
		if !ok {
			continue
		}
		flag := ordjson.GetStr(ca, "name")
		if flag == "" {
			continue
		}
		val := ""
		if overrides != nil {
			if v, ok := overrides.GetOK(flag); ok {
				val = stringify(v)
			}
		}
		if val == "" {
			if v, ok := ca.GetOK("value"); ok {
				val = stringify(v)
			} else if v, ok := ca.GetOK("default"); ok {
				val = stringify(v)
			}
		}
		if ordjson.GetStr(ca, "type") == "checkbox" {
			if val == "true" {
				built = append(built, flag)
			}
			continue
		}
		if val != "" {
			out := val
			if ordjson.GetStr(ca, "type") == "date" {
				out = FormatDateValue(out, ordjson.GetStr(ca, "format"))
			}
			built = append(built, flag, out)
		}
	}
	return built
}

// stringify mirrors Python's str() for the value shapes the frontend
// sends (strings, numbers, booleans).
func stringify(v any) string {
	switch x := v.(type) {
	case string:
		return x
	case json.Number:
		return x.String()
	case bool:
		if x {
			return "True"
		}
		return "False"
	case float64:
		return strconv.FormatFloat(x, 'g', -1, 64)
	case nil:
		return "None"
	default:
		return fmt.Sprint(x)
	}
}

// nextStepName allocates the next step number and display name
// ("N. Step Name"), matching _next_step_name.
func (r *Run) nextStepName(stepName string) (int, string) {
	r.StepCount++
	return r.StepCount, fmt.Sprintf("%d. %s", r.StepCount, stepName)
}

// appendOutput records a line in the run's output (and the given step's
// output, when set). Callers must hold m.mu.
func (m *Manager) appendOutput(r *Run, line string, stepOutput *[]string) {
	r.Output = append(r.Output, line)
	if stepOutput != nil {
		*stepOutput = append(*stepOutput, line)
	}
}

// spawnEnv builds the child environment: the server's environment plus
// the same UTF-8/unbuffered Python settings the Python server used.
func spawnEnv() []string {
	env := os.Environ()
	env = append(env,
		"PYTHONUTF8=1",
		"PYTHONIOENCODING=utf-8",
		"PYTHONUNBUFFERED=1",
	)
	return env
}

// runScript launches a script, streaming its combined output line by
// line into the run (and optionally one step's output). It mirrors
// run_script: with a positive timeout a watchdog kills the script and
// the run is reported as timed out; *result receives the return code
// (-1 on spawn failure).
func (m *Manager) runScript(r *Run, scriptPath string, args []string, result *int, timeout float64, stepOutput *[]string) {
	argv := m.BuildCommand(scriptPath, args)
	cmd := exec.Command(argv[0], argv[1:]...)
	cmd.Env = spawnEnv()
	setSysProcAttr(cmd)

	// One shared pipe for stdout and stderr keeps both streams
	// interleaved in arrival order, like Python's stderr=STDOUT.
	pr, pw, err := os.Pipe()
	if err != nil {
		m.recordSpawnError(r, result, err, stepOutput)
		return
	}
	cmd.Stdout = pw
	cmd.Stderr = pw

	if err := cmd.Start(); err != nil {
		pw.Close()
		pr.Close()
		m.recordSpawnError(r, result, err, stepOutput)
		return
	}
	// The parent's copy of the write end must close or EOF never
	// arrives; the child kept its own descriptor.
	pw.Close()

	m.mu.Lock()
	// A list, not a single slot: parallel workflow steps share the run
	// id, so cancelling must be able to reach every live script.
	r.procs = append(r.procs, cmd)
	// A cancel that arrived before this process was registered would
	// otherwise be missed, so honour it here too.
	if r.Cancelled && cmd.Process != nil {
		_ = cmd.Process.Kill()
	}
	m.mu.Unlock()

	done := make(chan struct{})
	var timedOutHere bool
	if timeout > 0 {
		go func() {
			select {
			case <-done:
				// The script finished first.
			case <-time.After(time.Duration(timeout * float64(time.Second))):
				m.mu.Lock()
				// Re-check under the lock: a hair-before-the-deadline
				// finish must not count as a timeout.
				select {
				case <-done:
					m.mu.Unlock()
					return
				default:
				}
				_ = cmd.Process.Kill()
				timedOutHere = true
				m.mu.Unlock()
			}
		}()
	}

	reader := bufio.NewReader(pr)
	for {
		line, err := reader.ReadString('\n')
		if line != "" {
			m.mu.Lock()
			m.appendOutput(r, toValidUTF8(line), stepOutput)
			m.mu.Unlock()
		}
		if err != nil {
			break
		}
	}
	close(done)
	pr.Close()
	waitErr := cmd.Wait()

	rc := exitCode(waitErr)
	m.mu.Lock()
	r.ReturnCode = &rc
	// Keep the run-level flag in sync: it stays true for the rest of the
	// run once any script hit its timeout.
	if timedOutHere {
		r.TimedOut = true
	}
	if result != nil {
		*result = rc
	}
	if timedOutHere {
		message := fmt.Sprintf("ERROR: Timed out after %gs and was killed.\n", timeout)
		m.appendOutput(r, message, stepOutput)
	}
	m.mu.Unlock()
}

func (m *Manager) recordSpawnError(r *Run, result *int, err error, stepOutput *[]string) {
	m.mu.Lock()
	message := fmt.Sprintf("ERROR: %s\n", err)
	m.appendOutput(r, message, stepOutput)
	neg := -1
	r.ReturnCode = &neg
	if result != nil {
		*result = -1
	}
	m.mu.Unlock()
}

// toValidUTF8 replaces invalid byte sequences with U+FFFD, matching the
// Python reader's errors="replace" decoding.
func toValidUTF8(s string) string {
	if isUTF8(s) {
		return s
	}
	return strings.ToValidUTF8(s, "\uFFFD")
}

func isUTF8(s string) bool {
	for i := 0; i < len(s); {
		c := s[i]
		if c < 0x80 {
			i++
			continue
		}
		var size int
		switch {
		case c&0xE0 == 0xC0:
			size = 2
		case c&0xF0 == 0xE0:
			size = 3
		case c&0xF8 == 0xF0:
			size = 4
		default:
			return false
		}
		if i+size > len(s) {
			return false
		}
		for j := 1; j < size; j++ {
			if s[i+j]&0xC0 != 0x80 {
				return false
			}
		}
		i += size
	}
	return true
}

// exitCode extracts a comparable exit code from a Wait result: nil means
// success (0), an ExitError carries the process's own code (negative for
// signals), anything else is a spawn/wait failure (-1).
func exitCode(err error) int {
	if err == nil {
		return 0
	}
	if ee, ok := err.(*exec.ExitError); ok && ee.ProcessState != nil {
		return ee.ProcessState.ExitCode()
	}
	return -1
}

// CancelRun kills a running run's script processes and marks the run
// cancelled. It reports whether the run was still in progress; a
// finished or unknown run cannot be cancelled.
func (m *Manager) CancelRun(runID string) bool {
	m.mu.Lock()
	defer m.mu.Unlock()
	r, ok := m.runs[runID]
	if !ok || finishedStatuses[r.Status] {
		return false
	}
	r.Cancelled = true
	for _, cmd := range r.procs {
		if cmd.Process != nil {
			_ = cmd.Process.Kill()
		}
	}
	r.Output = append(r.Output, CancelMessage)
	if r.WorkflowLog != nil {
		r.WorkflowLog = append(r.WorkflowLog, "[CANCEL] Run cancelled by user")
	}
	return true
}

// Prune drops finished runs so the registry cannot grow without bound.
// Finished runs stay pollable for FinishedRunTTLSeconds, at most
// MaxFinishedRuns of them are retained, and older ones remain available
// through run history.
func (m *Manager) Prune() {
	m.mu.Lock()
	defer m.mu.Unlock()
	now := float64(time.Now().Unix())
	type aged struct {
		id string
		at float64
	}
	finished := []aged{}
	for id, r := range m.runs {
		if finishedStatuses[r.Status] {
			// Entries without a finish stamp (injected by tests) get the
			// full grace period instead of being dropped immediately.
			at := r.FinishedAt
			if at == 0 {
				at = now
			}
			finished = append(finished, aged{id, at})
		}
	}
	// Oldest first, stable for equal finish times — same as the Python
	// sort, so the same runs get dropped when over the cap.
	for i := 1; i < len(finished); i++ {
		for j := i; j > 0 && finished[j].at < finished[j-1].at; j-- {
			finished[j], finished[j-1] = finished[j-1], finished[j]
		}
	}
	var remaining []aged
	for _, f := range finished {
		if f.at <= now-FinishedRunTTLSeconds {
			delete(m.runs, f.id)
		} else {
			remaining = append(remaining, f)
		}
	}
	if excess := len(remaining) - MaxFinishedRuns; excess > 0 {
		for _, f := range remaining[:excess] {
			delete(m.runs, f.id)
		}
	}
}
