package api

import (
	"os"
	"testing"
)

// TestHomeDir checks the fallback helper: on a normal system it returns
// the current user's home directory, never an empty string.
func TestHomeDir(t *testing.T) {
	dir := homeDir()
	if dir == "" {
		t.Fatal("homeDir returned an empty string")
	}
	if u, err := os.UserHomeDir(); err == nil {
		if dir != u {
			t.Fatalf("homeDir = %q, want %q", dir, u)
		}
	}
}
