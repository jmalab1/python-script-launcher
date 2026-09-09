package api

import (
	"math"
	"net/http"
	"strconv"
	"strings"

	"launchcontrol/internal/ordjson"
)

// maxPerPage caps paging so a bogus query string gets a sane response
// instead of serializing the whole table.
const maxPerPage = 200

// clampPaging normalizes page/per_page query values (history.py parity).
func clampPaging(pageRaw, perPageRaw string, defaultPerPage int) (int, int) {
	page := 1
	if n, err := strconv.Atoi(pageRaw); err == nil && n > 0 {
		page = n
	}
	perPage := defaultPerPage
	if n, err := strconv.Atoi(perPageRaw); err == nil && n > 0 {
		perPage = n
	}
	if perPage > maxPerPage {
		perPage = maxPerPage
	}
	return page, perPage
}

// entryTime is the time a history entry is shown for: when the run
// started. Legacy entries predating that field fall back to their
// timestamp.
func entryTime(entry *ordjson.OMap) float64 {
	if started, ok := ordjson.GetFloat(entry, "started_at"); ok {
		return started
	}
	t, _ := ordjson.GetFloat(entry, "timestamp")
	return t
}

// summarizeEntry adds the derived fields the history table renders:
// duration (None while running) and step tallies for workflows.
func summarizeEntry(entry *ordjson.OMap) *ordjson.OMap {
	summary := entry.Clone()
	startedAt, hasStarted := ordjson.GetFloat(entry, "started_at")
	timestamp, hasTimestamp := ordjson.GetFloat(entry, "timestamp")
	duration := any(nil)
	if ordjson.GetStr(entry, "status") == "running" {
		duration = nil
	} else if hasStarted && hasTimestamp && timestamp >= startedAt {
		duration = ordjson.Number(pyRound(timestamp-startedAt, 1))
	}
	summary.Set("duration", duration)

	if ordjson.GetStr(entry, "type") == "workflow" {
		if steps := ordjson.GetMap(entry, "steps"); steps != nil {
			total := steps.Len()
			okCount := 0
			for _, k := range steps.Keys() {
				if s, ok := steps.Get(k).(*ordjson.OMap); ok && ordjson.GetStr(s, "status") == "completed" {
					okCount++
				}
			}
			summary.Set("steps_total", total)
			summary.Set("steps_ok", okCount)
		}
	}
	return summary
}

// pyRound mirrors Python's round() (round-half-to-even), which a plain
// Go math.Round would not match at exact .5 boundaries.
func pyRound(x float64, ndigits int) float64 {
	out, err := strconv.ParseFloat(strconv.FormatFloat(x, 'f', ndigits, 64), 64)
	if err != nil {
		return x
	}
	if out == 0 {
		// -0.0 normalization, like Python round.
		out = 0
	}
	return out
}

// historyList serves GET /api/history with filters and paging.
func (a *API) historyList(r *http.Request) *ordjson.OMap {
	q := r.URL.Query()
	page, perPage := clampPaging(q.Get("page"), q.Get("per_page"), 15)
	typeFilter := q.Get("type")
	nameFilter := strings.ToLower(q.Get("name"))
	statusFilter := q.Get("status")
	since, hasSince := parseFloatOpt(q.Get("since"))
	until, hasUntil := parseFloatOpt(q.Get("until"))

	entries, err := a.DB.LoadHistory()
	if err != nil {
		entries = nil
	}
	filtered := make([]*ordjson.OMap, 0, len(entries))
	for _, e := range entries {
		if typeFilter != "" && ordjson.GetStr(e, "type") != typeFilter {
			continue
		}
		if nameFilter != "" && !strings.Contains(strings.ToLower(ordjson.GetStr(e, "name")), nameFilter) {
			continue
		}
		if statusFilter != "" && ordjson.GetStr(e, "status") != statusFilter {
			continue
		}
		if hasSince && entryTime(e) < since {
			continue
		}
		if hasUntil && entryTime(e) > until {
			continue
		}
		filtered = append(filtered, e)
	}

	// Newest first.
	sortHistory(filtered)
	total := len(filtered)
	start := (page - 1) * perPage
	end := start + perPage
	if start > total {
		start = total
	}
	if end > total {
		end = total
	}

	pageEntries := make([]any, 0, end-start)
	for _, e := range filtered[start:end] {
		pageEntries = append(pageEntries, summarizeEntry(e))
	}
	return ordjson.New().
		Set("entries", pageEntries).
		Set("total", total).
		Set("page", page).
		Set("per_page", perPage).
		Set("pages", (total+perPage-1)/perPage)
}

// sortHistory orders newest-first by timestamp (matching the Python
// sort on timestamp).
func sortHistory(entries []*ordjson.OMap) {
	for i := 1; i < len(entries); i++ {
		for j := i; j > 0; j-- {
			a, _ := ordjson.GetFloat(entries[j], "timestamp")
			b, _ := ordjson.GetFloat(entries[j-1], "timestamp")
			if (a > b) || (a == b && false) {
				entries[j], entries[j-1] = entries[j-1], entries[j]
			} else {
				break
			}
		}
	}
}

// historyDetail matches by entry id first, then run id; a type filter
// is preferred over untyped matches; the newest wins.
func (a *API) historyDetail(entryKey, typeFilter string) *ordjson.OMap {
	entries, err := a.DB.LoadHistory()
	if err != nil {
		return nil
	}

	var matches []*ordjson.OMap
	for _, e := range entries {
		if ordjson.GetStr(e, "id") == entryKey || ordjson.GetStr(e, "run_id") == entryKey {
			matches = append(matches, e)
		}
	}
	if len(matches) == 0 {
		return nil
	}

	if typeFilter != "" {
		var typed []*ordjson.OMap
		for _, e := range matches {
			if ordjson.GetStr(e, "type") == typeFilter {
				typed = append(typed, e)
			}
		}
		if len(typed) > 0 {
			matches = typed
		}
	}
	sortHistory(matches)
	return matches[0]
}

// HistoryDelete removes one entry by id, falling back to run id.
func (a *API) HistoryDelete(entryKey string) *ordjson.OMap {
	removed := a.DB.RemoveHistory(func(e *ordjson.OMap) bool {
		return ordjson.GetStr(e, "id") == entryKey
	})
	if removed == 0 {
		a.DB.RemoveHistory(func(e *ordjson.OMap) bool {
			return ordjson.GetStr(e, "run_id") == entryKey
		})
	}
	return ordjson.New().Set("ok", true)
}

// HistoryBulkDelete removes the given ids and reports the count.
func (a *API) HistoryBulkDelete(data *ordjson.OMap) *ordjson.OMap {
	ids := map[string]bool{}
	for _, raw := range ordjson.GetArr(data, "ids") {
		if s, ok := raw.(string); ok {
			ids[s] = true
		}
	}
	removed := a.DB.RemoveHistory(func(e *ordjson.OMap) bool {
		return ids[ordjson.GetStr(e, "id")]
	})
	return ordjson.New().Set("ok", true).Set("removed", removed)
}

// HistoryClear empties the whole run history.
func (a *API) HistoryClear() *ordjson.OMap {
	a.DB.ReplaceHistory([]*ordjson.OMap{})
	return ordjson.New().Set("ok", true)
}

func parseFloatOpt(s string) (float64, bool) {
	if s == "" {
		return 0, false
	}
	f, err := strconv.ParseFloat(s, 64)
	if err != nil {
		return 0, false
	}
	_ = math.NaN
	return f, true
}
