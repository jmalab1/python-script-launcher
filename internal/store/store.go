// Package store persists the app's collections in SQLite.
//
// Every record is kept as a JSON blob (the schema the Python app used),
// so the Go server reads and writes the same data/launcher.db with no
// migration. Collections are loaded whole and saved whole, matching the
// original semantics; per-collection locks serialise read-modify-write
// cycles exactly like the Python RLocks did.
package store

import (
	"crypto/rand"
	"database/sql"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"log/slog"
	"os"
	"path/filepath"
	"strings"
	"sync"
	"time"

	_ "modernc.org/sqlite"
)

// Collections map to SQLite tables of the same name.
var collections = map[string]bool{
	"profiles": true, "workflows": true, "history": true,
	"audit": true, "schedules": true,
}

// AuditMax caps the audit trail; older entries are dropped.
const AuditMax = 1000

// DB is a handle to the launcher database.
type DB struct {
	sql *sql.DB
	// dataDir holds legacy *.json files migrated on first open.
	dataDir string

	locksMu sync.Mutex
	locks   map[string]*sync.Mutex
}

// NewID returns a random 32-char hex id, matching uuid.uuid4().hex from
// the Python implementation.
func NewID() string {
	var b [16]byte
	if _, err := rand.Read(b[:]); err != nil {
		panic(fmt.Sprintf("cannot read random bytes: %v", err))
	}
	return hex.EncodeToString(b[:])
}

// Open opens (and creates if needed) the database, initialising the
// schema and running the legacy JSON-file migration.
func Open(dbPath, dataDir string) (*DB, error) {
	if err := os.MkdirAll(dataDir, 0o755); err != nil {
		return nil, err
	}
	repairOwnership(dbPath)

	dsn := "file:" + dbPath + "?_pragma=busy_timeout(5000)&_pragma=journal_mode(WAL)&_pragma=foreign_keys(1)"
	sqlDB, err := sql.Open("sqlite", dsn)
	if err != nil {
		return nil, err
	}
	// A single connection serialises all access, mirroring the Python
	// server's one-connection-at-a-time pattern and avoiding SQLITE_BUSY
	// entirely (the workload is small: whole-collection reads/writes).
	sqlDB.SetMaxOpenConns(1)

	db := &DB{sql: sqlDB, dataDir: dataDir, locks: map[string]*sync.Mutex{}}
	if err := db.initSchema(); err != nil {
		sqlDB.Close()
		return nil, err
	}
	db.migrateLegacy()
	return db, nil
}

// Close releases the database handle.
func (db *DB) Close() error { return db.sql.Close() }

// repairOwnership is a best-effort fix for a read-only DB file left
// behind by another user (for example a root-run instance on POSIX).
// It never fails startup; writes failing later give a clearer error.
func repairOwnership(dbPath string) {
	info, err := os.Stat(dbPath)
	if err != nil {
		return
	}
	if info.Mode().Perm()&0o200 != 0 {
		return
	}
	// Try to add owner-write. On POSIX this only works if we own the
	// file or have the rights; on Windows it usually succeeds.
	if err := os.Chmod(dbPath, info.Mode().Perm()|0o200); err != nil {
		slog.Warn("Cannot make database writable", "path", dbPath, "err", err)
	} else {
		slog.Info("Fixed permissions of read-only database", "path", dbPath)
	}
}

func (db *DB) initSchema() error {
	_, err := db.sql.Exec(`
        CREATE TABLE IF NOT EXISTS profiles (
            id TEXT PRIMARY KEY,
            json TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS workflows (
            id TEXT PRIMARY KEY,
            json TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS history (
            id TEXT PRIMARY KEY,
            run_id TEXT NOT NULL,
            type TEXT NOT NULL,
            json TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_history_run_id ON history(run_id);
        CREATE INDEX IF NOT EXISTS idx_history_type ON history(type);
        CREATE TABLE IF NOT EXISTS audit (
            id TEXT PRIMARY KEY,
            json TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS schedules (
            id TEXT PRIMARY KEY,
            json TEXT NOT NULL
        );`)
	return err
}

// legacyFiles are the pre-SQLite storage files; they are imported once
// when the matching table is still empty.
var legacyFiles = map[string]string{
	"profiles":  "profiles.json",
	"workflows": "workflows.json",
	"history":   "history.json",
	"audit":     "audit.json",
}

func (db *DB) migrateLegacy() {
	for collection, filename := range legacyFiles {
		items, err := db.Load(collection)
		if err != nil || len(items) > 0 {
			continue
		}
		raw, err := os.ReadFile(filepath.Join(db.dataDir, filename))
		if err != nil {
			continue
		}
		var data []map[string]any
		dec := json.NewDecoder(strings.NewReader(string(raw)))
		dec.UseNumber()
		if err := dec.Decode(&data); err != nil {
			slog.Warn("Failed to read legacy file", "file", filename, "err", err)
			continue
		}
		if len(data) == 0 {
			continue
		}
		slog.Info("Migrating legacy file into SQLite", "file", filename, "records", len(data))
		if err := db.Save(collection, data); err != nil {
			slog.Warn("Legacy migration failed", "file", filename, "err", err)
		}
	}
}

// Collection returns the per-collection write lock, creating it on
// demand. Handlers wrap whole read-modify-write cycles in this lock so
// concurrent edits cannot silently overwrite each other.
func (db *DB) Collection(collection string) *sync.Mutex {
	db.locksMu.Lock()
	defer db.locksMu.Unlock()
	mu, ok := db.locks[collection]
	if !ok {
		mu = &sync.Mutex{}
		db.locks[collection] = mu
	}
	return mu
}

// WithCollection runs fn while holding the collection's write lock.
func (db *DB) WithCollection(collection string, fn func()) {
	mu := db.Collection(collection)
	mu.Lock()
	defer mu.Unlock()
	fn()
}

// Load returns every record in the collection, in insertion (rowid)
// order. All numbers arrive as json.Number so re-serialising is
// loss-free.
func (db *DB) Load(collection string) ([]map[string]any, error) {
	table, err := tableFor(collection)
	if err != nil {
		return nil, err
	}
	rows, err := db.sql.Query(`SELECT json FROM "` + table + `" ORDER BY rowid`)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	var out []map[string]any
	for rows.Next() {
		var blob string
		if err := rows.Scan(&blob); err != nil {
			return nil, err
		}
		item, err := unmarshalItem(blob)
		if err != nil {
			return nil, err
		}
		out = append(out, item)
	}
	return out, rows.Err()
}

func unmarshalItem(blob string) (map[string]any, error) {
	dec := json.NewDecoder(strings.NewReader(blob))
	dec.UseNumber()
	var item map[string]any
	if err := dec.Decode(&item); err != nil {
		return nil, err
	}
	return item, nil
}

// Save replaces the whole collection. Items without an "id" get a new
// random hex id, like the Python implementation. The delete + inserts
// run in one transaction so a crash cannot leave the collection empty.
func (db *DB) Save(collection string, items []map[string]any) error {
	table, err := tableFor(collection)
	if err != nil {
		return err
	}
	tx, err := db.sql.Begin()
	if err != nil {
		return err
	}
	defer tx.Rollback()
	if _, err := tx.Exec(`DELETE FROM "` + table + `"`); err != nil {
		return err
	}
	for _, item := range items {
		if item["id"] == nil || item["id"] == "" {
			item["id"] = NewID()
		}
		blob, err := json.Marshal(item)
		if err != nil {
			return err
		}
		if table == "history" {
			_, err = tx.Exec(
				`INSERT INTO "history" (id, run_id, type, json) VALUES (?, ?, ?, ?)`,
				toString(item["id"]), toString(item["run_id"]), toString(item["type"]), string(blob),
			)
		} else {
			_, err = tx.Exec(
				`INSERT INTO "`+table+`" (id, json) VALUES (?, ?)`,
				toString(item["id"]), string(blob),
			)
		}
		if err != nil {
			return err
		}
	}
	return tx.Commit()
}

func toString(v any) string {
	if v == nil {
		return ""
	}
	if s, ok := v.(string); ok {
		return s
	}
	return fmt.Sprint(v)
}

// nowSeconds returns the current time as float seconds since the epoch,
// matching Python's time.time() shape used throughout the stored data.
func nowSeconds() float64 {
	return float64(time.Now().UnixNano()) / 1e9
}

func tableFor(collection string) (string, error) {
	if !collections[collection] {
		return "", fmt.Errorf("unknown collection: %q", collection)
	}
	return collection, nil
}
