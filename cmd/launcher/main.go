// Command launcher is Launch Control's compiled server: port of
// launcher.py's main(), with the same defaults (127.0.0.1:8765,
// auto-open browser on Windows, graceful Ctrl+C shutdown).
package main

import (
	"context"
	"flag"
	"fmt"
	"log/slog"
	"net"
	"net/http"
	"os"
	"os/signal"
	"runtime"
	"syscall"
	"time"

	"launchcontrol/internal/api"
	"launchcontrol/internal/applog"
	"launchcontrol/internal/config"
	"launchcontrol/internal/pythonrt"
	"launchcontrol/internal/runner"
	"launchcontrol/internal/scheduler"
	"launchcontrol/internal/store"
)

func main() {
	port := flag.Int("port", config.DefaultPort, "listen port (0 picks a free port)")
	flag.Parse()

	dataDir := config.DataDir()
	rotator := applog.Setup(config.LogFile(), config.LogMaxBytes, config.LogBackupCount)
	if rotator != nil {
		defer rotator.Close()
	}

	if err := os.MkdirAll(dataDir, 0o755); err != nil {
		slog.Error("Cannot create data directory", "dir", dataDir, "err", err)
		shutdown(1)
	}

	db, err := store.Open(config.DBPath(), dataDir)
	if err != nil {
		slog.Error("Cannot open database", "path", config.DBPath(), "err", err)
		shutdown(1)
	}
	defer db.Close()

	runs := runner.NewManager(db, func() (string, error) {
		return pythonrt.Interpreter()
	})
	sched := scheduler.New(db, runs)

	listener, err := net.Listen("tcp", net.JoinHostPort("127.0.0.1", fmt.Sprint(*port)))
	if err != nil {
		slog.Error("Could not start server on port", "port", *port, "err", err)
		slog.Error("Is another instance of Launch Control already running?")
		// Windows console windows close on exit, so the user would never
		// read the error without a pause (Python did the same).
		if runtime.GOOS == "windows" {
			fmt.Println("Press Enter to exit...")
			fmt.Scanln()
		}
		shutdown(1)
	}
	defer listener.Close()
	_ = listener.Addr().(net.Addr)

	server := &http.Server{Handler: api.New(db, runs, sched, dataDir, config.LogFile())}

	// The scheduler starts only once the server is bound, mirroring the
	// Python main().
	sched.Start()
	defer sched.Stop()

	portNum := listener.Addr().(*net.TCPAddr).Port
	slog.Info(fmt.Sprintf("Launch Control running at http://127.0.0.1:%d", portNum))
	slog.Info("Press Ctrl+C to stop.")

	if runtime.GOOS == "windows" {
		// Open the browser shortly after the server is reachable, like
		// the Python timer did.
		go func() {
			time.Sleep(1 * time.Second)
			openBrowser(fmt.Sprintf("http://127.0.0.1:%d", portNum))
		}()
	}

	// Serve on the main goroutine, stopping on Ctrl+C.
	go func() {
		sig := make(chan os.Signal, 1)
		signal.Notify(sig, os.Interrupt, syscall.SIGTERM)
		<-sig
		slog.Info("Shutting down.")
		ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
		defer cancel()
		server.Shutdown(ctx)
	}()
	if err := server.Serve(listener); err != nil && err != http.ErrServerClosed {
		slog.Error("Server error", "err", err)
		shutdown(1)
	}
}

// shutdown exits without leaving the Windows console reader hanging.
func shutdown(code int) {
	os.Exit(code)
}
