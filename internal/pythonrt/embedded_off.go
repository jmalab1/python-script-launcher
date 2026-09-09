//go:build !embedded

package pythonrt

// embedded returns the archive bytes only in release builds, which are
// tagged with -tags embedded after the archive file is put in place.
func embedded() ([]byte, bool) { return nil, false }
