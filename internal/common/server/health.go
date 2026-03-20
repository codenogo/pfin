package server

import (
	"context"
	"net/http"
	"time"
)

// DBPinger is an interface for checking database connectivity.
type DBPinger interface {
	Ping(ctx context.Context) error
}

var startTime = time.Now()

// HealthHandler returns a handler that reports application health.
func HealthHandler(db DBPinger) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		dbStatus := "ok"
		status := http.StatusOK

		if db != nil {
			ctx, cancel := context.WithTimeout(r.Context(), 2*time.Second)
			defer cancel()
			if err := db.Ping(ctx); err != nil {
				dbStatus = "error"
				status = http.StatusServiceUnavailable
			}
		} else {
			dbStatus = "unavailable"
		}

		JSON(w, status, map[string]string{
			"status":   statusText(status),
			"uptime":   time.Since(startTime).Truncate(time.Second).String(),
			"database": dbStatus,
		})
	}
}

func statusText(status int) string {
	if status == http.StatusOK {
		return "ok"
	}
	return "error"
}
