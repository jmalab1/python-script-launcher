package api

import (
	"net/http"
	"strings"

	"launchcontrol/internal/ordjson"
)

// auditListFields are the fields the audit table receives for list
// rows; detail responses return the full entry (Python _LIST_FIELDS).
var auditListFields = []string{"id", "timestamp", "action", "entity_type", "entity_id", "name", "details"}

// auditList serves GET /api/audit with filters and paging.
func (a *API) auditList(r *http.Request) *ordjson.OMap {
	q := r.URL.Query()
	page, perPage := clampPaging(q.Get("page"), q.Get("per_page"), 20)
	actionFilter := q.Get("action")
	entityFilter := q.Get("entity")
	nameFilter := strings.ToLower(q.Get("name"))
	since, hasSince := parseFloatOpt(q.Get("since"))
	until, hasUntil := parseFloatOpt(q.Get("until"))

	entries, err := a.DB.LoadAudit()
	if err != nil {
		entries = nil
	}
	filtered := make([]*ordjson.OMap, 0, len(entries))
	for _, e := range entries {
		if actionFilter != "" && ordjson.GetStr(e, "action") != actionFilter {
			continue
		}
		if entityFilter != "" && ordjson.GetStr(e, "entity_type") != entityFilter {
			continue
		}
		if nameFilter != "" && !strings.Contains(strings.ToLower(ordjson.GetStr(e, "name")), nameFilter) {
			continue
		}
		ts, hasTS := ordjson.GetFloat(e, "timestamp")
		if hasSince && (!hasTS || ts < since) {
			continue
		}
		if hasUntil && (!hasTS || ts > until) {
			continue
		}
		filtered = append(filtered, e)
	}
	sortAudit(filtered)
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
		pageEntries = append(pageEntries, summarizeAuditEntry(e))
	}
	return ordjson.New().
		Set("entries", pageEntries).
		Set("total", total).
		Set("page", page).
		Set("per_page", perPage).
		Set("pages", (total+perPage-1)/perPage)
}

func sortAudit(entries []*ordjson.OMap) {
	for i := 1; i < len(entries); i++ {
		for j := i; j > 0; j-- {
			a, _ := ordjson.GetFloat(entries[j], "timestamp")
			b, _ := ordjson.GetFloat(entries[j-1], "timestamp")
			if a > b {
				entries[j], entries[j-1] = entries[j-1], entries[j]
			} else {
				break
			}
		}
	}
}

// summarizeAuditEntry keeps only the list-view fields.
func summarizeAuditEntry(entry *ordjson.OMap) *ordjson.OMap {
	out := ordjson.New()
	for _, k := range auditListFields {
		if v, ok := entry.GetOK(k); ok {
			out.Set(k, v)
		}
	}
	return out
}

// auditDetail returns a full audit entry by id.
func (a *API) auditDetail(entryID string) *ordjson.OMap {
	entries, err := a.DB.LoadAudit()
	if err != nil {
		return nil
	}
	for _, e := range entries {
		if ordjson.GetStr(e, "id") == entryID {
			return e
		}
	}
	return nil
}
