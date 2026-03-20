package errs

import (
	"errors"
	"fmt"
	"net/http"
	"testing"
)

func TestNew(t *testing.T) {
	e := New(CodeValidation, "name is required")
	if e.Code != CodeValidation {
		t.Errorf("Code = %q, want %q", e.Code, CodeValidation)
	}
	if e.Message != "name is required" {
		t.Errorf("Message = %q, want %q", e.Message, "name is required")
	}
	if e.Err != nil {
		t.Error("Err should be nil")
	}
}

func TestWrap(t *testing.T) {
	inner := fmt.Errorf("connection refused")
	e := Wrap(CodeInternal, "database error", inner)
	if !errors.Is(e, inner) {
		t.Error("Unwrap should return the inner error")
	}
	if e.Err != inner {
		t.Error("Err should be the inner error")
	}
}

func TestError_String(t *testing.T) {
	e := New(CodeNotFound, "user not found")
	expected := "NOT_FOUND: user not found"
	if e.Error() != expected {
		t.Errorf("Error() = %q, want %q", e.Error(), expected)
	}

	inner := fmt.Errorf("pg error")
	e2 := Wrap(CodeInternal, "query failed", inner)
	if e2.Error() != "INTERNAL_ERROR: query failed: pg error" {
		t.Errorf("Error() = %q", e2.Error())
	}
}

func TestHelpers(t *testing.T) {
	cases := []struct {
		name string
		err  *DomainError
		code string
	}{
		{"NotFound", NotFound("user", "abc"), CodeNotFound},
		{"Conflict", Conflict("duplicate"), CodeConflict},
		{"Validation", Validation("bad input"), CodeValidation},
		{"Unauthorized", Unauthorized(), CodeUnauthorized},
		{"Forbidden", Forbidden("not allowed"), CodeForbidden},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			if tc.err.Code != tc.code {
				t.Errorf("Code = %q, want %q", tc.err.Code, tc.code)
			}
		})
	}
}

func TestHTTPStatus(t *testing.T) {
	cases := []struct {
		code   string
		status int
	}{
		{CodeValidation, http.StatusBadRequest},
		{CodeUnbalancedEntry, http.StatusBadRequest},
		{CodeNotFound, http.StatusNotFound},
		{CodeConflict, http.StatusConflict},
		{CodeUnauthorized, http.StatusUnauthorized},
		{CodeForbidden, http.StatusForbidden},
		{CodeInternal, http.StatusInternalServerError},
		{"UNKNOWN", http.StatusInternalServerError},
	}
	for _, tc := range cases {
		t.Run(tc.code, func(t *testing.T) {
			e := New(tc.code, "test")
			if e.HTTPStatus() != tc.status {
				t.Errorf("HTTPStatus() = %d, want %d", e.HTTPStatus(), tc.status)
			}
		})
	}
}

func TestErrorsAs(t *testing.T) {
	e := NotFound("account", "123")
	var domErr *DomainError
	if !errors.As(e, &domErr) {
		t.Error("errors.As should match DomainError")
	}
	if domErr.Code != CodeNotFound {
		t.Errorf("Code = %q, want %q", domErr.Code, CodeNotFound)
	}
}
