//go:build !windows

package api

// listDrives returns nothing on non-Windows systems; "/" is its own
// root there.
func listDrives() []any { return nil }
