package store

import (
	"crypto/sha256"
	"encoding/hex"
	"log/slog"
	"sort"

	"launchcontrol/internal/ordjson"
)

// RecordAudit appends a tamper-evident entry describing a change and
// trims the trail to AuditMax, mirroring storage.record_audit from the
// Python app.
//
// before/after/details are optional; pass nil when a field does not
// apply so the stored JSON matches the Python shape (missing key, not
// null).
func (db *DB) RecordAudit(action, entityType, entityID, name string, before, after, details *ordjson.OMap) *ordjson.OMap {
	entry := ordjson.New().
		Set("id", NewID()).
		Set("timestamp", ordjson.Number(nowSeconds())).
		Set("action", action).
		Set("entity_type", entityType).
		Set("entity_id", entityID).
		Set("name", name)
	if before != nil {
		entry.Set("before", before)
	}
	if after != nil {
		entry.Set("after", after)
	}
	if details != nil {
		entry.Set("details", details)
	}
	// The hash is stored with the entry so tampering can be detected
	// later (append_audit in the Python app).
	entry.Set("_hash", HashEntry(entry))

	entries, _ := db.LoadAudit()
	entries = append(entries, entry)
	if len(entries) > AuditMax {
		entries = entries[len(entries)-AuditMax:]
	}
	if err := db.Save("audit", entries); err != nil {
		slog.Error("Failed to save audit trail", "err", err)
	}
	return entry
}

// LoadAudit returns the audit trail, backfilling missing ids and hashes
// the way Python's load_audit did (older entries may lack either).
func (db *DB) LoadAudit() ([]*ordjson.OMap, error) {
	entries, err := db.Load("audit")
	if err != nil {
		return nil, err
	}

	changed := false
	for _, entry := range entries {
		if ordjson.GetStr(entry, "id") == "" {
			entry.Set("id", NewID())
			changed = true
		}
		if entry.Get("_hash") == nil {
			entry.Set("_hash", HashEntry(entry))
			changed = true
		}
	}
	if changed {
		if err := db.Save("audit", entries); err != nil {
			slog.Warn("Failed to backfill audit entries", "err", err)
		}
	}
	return entries, nil
}

// ChangedFields returns the sorted top-level field names that differ
// between before and after, or nil when there is no before state.
func ChangedFields(before, after *ordjson.OMap) []string {
	if before == nil {
		return nil
	}

	seen := map[string]bool{}
	for _, k := range before.Keys() {
		seen[k] = true
	}
	for _, k := range after.Keys() {
		seen[k] = true
	}

	var changed []string
	for k := range seen {
		if !jsonEqual(before.Get(k), after.Get(k)) {
			changed = append(changed, k)
		}
	}
	// sort.Strings gives codepoint order, same as Python's sorted().
	sort.Strings(changed)
	return changed
}

func jsonEqual(a, b any) bool {
	return canonicalJSON(Normalize(a)) == canonicalJSON(Normalize(b))
}

// HashEntry computes the tamper-evident hash of an audit entry,
// byte-compatible with Python's sha256 over
// json.dumps(entry, sort_keys=True, ensure_ascii=False).
func HashEntry(entry *ordjson.OMap) string {
	normalized := Normalize(entry).(*ordjson.OMap)
	clean := normalized.Clone()
	clean.Delete("_hash")
	sum := sha256.Sum256([]byte(canonicalJSON(clean)))
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
		if HashEntry(entry) != ordjson.GetStr(entry, "_hash") {
			tampered = append(tampered, ordjson.GetStr(entry, "id"))
		}
	}
	return len(tampered) == 0, tampered
}
