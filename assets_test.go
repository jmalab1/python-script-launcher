package assets

import (
	"io/fs"
	"testing"
)

// TestIndexHTML checks that the embed hook has real content.
func TestIndexHTML(t *testing.T) {
	page := IndexHTML()
	if len(page) == 0 {
		t.Fatal("embedded index.html is empty")
	}
}

// TestStatic checks that the embedded static tree can be opened and
// read, and that paths outside static/ never resolve.
func TestStatic(t *testing.T) {
	sub := Static()

	entries, err := fs.ReadDir(sub, ".")
	if err != nil {
		t.Fatal(err)
	}
	if len(entries) == 0 {
		t.Fatal("embedded static/ tree is empty")
	}

	if _, err := fs.ReadFile(sub, "../index.html"); err == nil {
		t.Fatal("path outside static/ should not be readable")
	}
}
