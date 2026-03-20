package server

import (
	"encoding/json"
	"fmt"
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/codenogo/pfin/pkg/errs"
)

func TestJSON(t *testing.T) {
	w := httptest.NewRecorder()
	JSON(w, http.StatusOK, map[string]string{"status": "ok"})

	if w.Code != http.StatusOK {
		t.Errorf("status = %d, want %d", w.Code, http.StatusOK)
	}
	if ct := w.Header().Get("Content-Type"); ct != "application/json" {
		t.Errorf("Content-Type = %q, want application/json", ct)
	}

	var body map[string]string
	json.NewDecoder(w.Body).Decode(&body)
	if body["status"] != "ok" {
		t.Errorf("body = %v", body)
	}
}

func TestError_DomainError(t *testing.T) {
	cases := []struct {
		err    *errs.DomainError
		status int
		code   string
	}{
		{errs.NotFound("user", "123"), http.StatusNotFound, errs.CodeNotFound},
		{errs.Validation("bad input"), http.StatusBadRequest, errs.CodeValidation},
		{errs.Conflict("duplicate"), http.StatusConflict, errs.CodeConflict},
		{errs.Unauthorized(), http.StatusUnauthorized, errs.CodeUnauthorized},
		{errs.Forbidden("no access"), http.StatusForbidden, errs.CodeForbidden},
	}
	for _, tc := range cases {
		t.Run(tc.code, func(t *testing.T) {
			w := httptest.NewRecorder()
			Error(w, tc.err)
			if w.Code != tc.status {
				t.Errorf("status = %d, want %d", w.Code, tc.status)
			}
			var body map[string]string
			json.NewDecoder(w.Body).Decode(&body)
			if body["code"] != tc.code {
				t.Errorf("code = %q, want %q", body["code"], tc.code)
			}
		})
	}
}

func TestError_GenericError(t *testing.T) {
	w := httptest.NewRecorder()
	Error(w, fmt.Errorf("something went wrong"))
	if w.Code != http.StatusInternalServerError {
		t.Errorf("status = %d, want 500", w.Code)
	}
}
