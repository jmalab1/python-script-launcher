//go:build embedded

package pythonrt

import _ "embed"

// The python-build-standalone install_only archive, swapped in by the
// release build for each target platform.
//
//go:embed runtime.tar.gz
var runtimeArchive []byte

func embedded() ([]byte, bool) { return runtimeArchive, len(runtimeArchive) > 0 }
