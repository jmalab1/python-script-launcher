package store

import (
	"crypto/sha256"
	"encoding/hex"
	"log/slog"
	"sort"
)

// RecordAudit appends a tamper-evident entry describing a change and
// trims the trail to AuditMax, mirroring storage.record_audit from the
// Python app.
//
// before/after/details are optional; omit a field entirely (nil) when
// it does not apply so the stored JSON matches the Python shape.
func (db *DB) RecordAudit(action, entityType, entityID, name string, before, after, details map[string]any) map[string]any {
	entry := map[string]any{
		"id":          NewID(),
		"timestamp":   nowSeconds(),
		"action":      action,
		"entity_type": entityType,
		"entity_id":   entityID,
		"name":        name,
	}
	if before != nil {
		entry["before"] = before
	}
	if after != nil {
		entry["after"] = after
	}
	if details != nil {
		entry["details"] = details
	}
	// The hash is stored with the entry so tampering can be detected
	// later (append_audit in the Python app).
	entry["_hash"] = HashEntry(entry)

	entries, _ := db.Load("audit")
	entries = append(entries, entry)
	if len(entries) > AuditMax {
		entries = entries[len(entries)-AuditMax:]
	}
	if err := db.Save("audit", entries); err != nil {
		slog.Error("Failed to save audit trail", "err", err)
	}
	return entry
}

// ChangedFields returns the sorted top-level field names that differ
// between before and after, or nil when there is no before state.
func ChangedFields(before, after map[string]any) []string {
	if before == nil {
		return nil
	}
	seen := map[string]bool{}
	for k := range before {
		seen[k] = true
	}
	for k := range after {
		seen[k] = true
	}
	var changed []string
	for k := range seen {
		if !jsonEqual(before[k], after[k]) {
			changed = append(changed, k)
		}
	}
	// sort.Strings gives codepoint order, same as Python's sorted().
	sort.Strings(changed)
	return changed
}

func jsonEqual(a, b any) bool {
	// Numbers may arrive as json.Number or float64 depending on origin;
	// compare their canonical text so 1 and 1.0 count as equal values
	// the way Python's == on parsed JSON would not distinguish them.
	return canonicalJSON(Normalize(a)) == canonicalJSON(Normalize(b))
}

// HashEntry computes the tamper-evident hash of an audit entry,
// byte-compatible with Python's sha256 over
// json.dumps(entry, sort_keys=True, ensure_ascii=False).
func HashEntry(entry map[string]any) string {
	normalized := Normalize(entry)
	if m, ok := normalized.(map[string]any); ok {
		delete(m, "_hash")
		normalized = m
	}
	sum := sha256.Sum256([]byte(canonicalJSON(normalized)))
	return hex.EncodeToString(sum[:])
}

// VerifyAuditIntegrity re-checks every stored hash. It reports whether
// the trail is intact and lists the ids of any tampered entries.
func (db *DB) VerifyAuditIntegrity() (bool, []string) {
	entries, err := db.Load("audit")
	if err != nil {
		return false, nil
	}
	var tampered []string
	for _, entry := range entries {
		if HashEntry(entry) != asString(entry["_hash"]) {
			tampered = append(tampered, asString(entry["id"]))
		}
	}
	return len(tampered) == 0, tampered
}

func asString(v any) string {
	if s, ok := v.(string); ok {
		return s
	}
	return ""
}
