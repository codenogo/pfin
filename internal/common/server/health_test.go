package server

import (
	"context"
	"encoding/json"
	"fmt"
	"net/http"
	"net/http/httptest"
	"testing"
)

type mockDB struct{ healthy bool }

func (m *mockDB) Ping(ctx context.Context) error {
	if !m.healthy {
		return fmt.Errorf("db down")
	}
	return nil
}

func TestHealthHandler_Healthy(t *testing.T) {
	handler := HealthHandler(&mockDB{healthy: true})
	w := httptest.NewRecorder()
	r := httptest.NewRequest(http.MethodGet, "/health", nil)

	handler(w, r)

	if w.Code != http.StatusOK {
		t.Errorf("status = %d, want 200", w.Code)
	}
	var body map[string]string
	json.NewDecoder(w.Body).Decode(&body)
	if body["status"] != "ok" {
		t.Errorf("status = %q, want ok", body["status"])
	}
	if body["database"] != "ok" {
		t.Errorf("database = %q, want ok", body["database"])
	}
	if body["uptime"] == "" {
		t.Error("uptime should not be empty")
	}
}

func TestHealthHandler_Unhealthy(t *testing.T) {
	handler := HealthHandler(&mockDB{healthy: false})
	w := httptest.NewRecorder()
	r := httptest.NewRequest(http.MethodGet, "/health", nil)

	handler(w, r)

	if w.Code != http.StatusServiceUnavailable {
		t.Errorf("status = %d, want 503", w.Code)
	}
}

func TestHealthHandler_NilDB(t *testing.T) {
	handler := HealthHandler(nil)
	w := httptest.NewRecorder()
	r := httptest.NewRequest(http.MethodGet, "/health", nil)

	handler(w, r)

	if w.Code != http.StatusOK {
		t.Errorf("status = %d, want 200", w.Code)
	}
	var body map[string]string
	json.NewDecoder(w.Body).Decode(&body)
	if body["database"] != "unavailable" {
		t.Errorf("database = %q, want unavailable", body["database"])
	}
}
