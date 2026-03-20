package auth

import (
	"encoding/json"
	"fmt"
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/google/uuid"
)

func mockValidator(valid bool, userID uuid.UUID, email string) TokenValidator {
	return func(tokenStr string) (uuid.UUID, string, error) {
		if !valid {
			return uuid.Nil, "", fmt.Errorf("invalid token")
		}
		return userID, email, nil
	}
}

func TestJWTMiddleware_ValidToken(t *testing.T) {
	uid := uuid.New()
	middleware := JWTMiddleware(mockValidator(true, uid, "test@example.com"))

	var capturedUser *UserContext
	handler := middleware(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		uc, err := UserFromContext(r.Context())
		if err != nil {
			t.Fatalf("UserFromContext: %v", err)
		}
		capturedUser = uc
		w.WriteHeader(http.StatusOK)
	}))

	req := httptest.NewRequest(http.MethodGet, "/", nil)
	req.Header.Set("Authorization", "Bearer valid-token")
	w := httptest.NewRecorder()

	handler.ServeHTTP(w, req)

	if w.Code != http.StatusOK {
		t.Errorf("status = %d, want 200", w.Code)
	}
	if capturedUser == nil {
		t.Fatal("user context should be set")
	}
	if capturedUser.UserID != uid {
		t.Errorf("UserID = %v, want %v", capturedUser.UserID, uid)
	}
	if capturedUser.Email != "test@example.com" {
		t.Errorf("Email = %q", capturedUser.Email)
	}
}

func TestJWTMiddleware_MissingHeader(t *testing.T) {
	middleware := JWTMiddleware(mockValidator(true, uuid.New(), "a@b.com"))
	handler := middleware(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		t.Fatal("handler should not be called")
	}))

	req := httptest.NewRequest(http.MethodGet, "/", nil)
	w := httptest.NewRecorder()
	handler.ServeHTTP(w, req)

	if w.Code != http.StatusUnauthorized {
		t.Errorf("status = %d, want 401", w.Code)
	}
}

func TestJWTMiddleware_InvalidToken(t *testing.T) {
	middleware := JWTMiddleware(mockValidator(false, uuid.Nil, ""))
	handler := middleware(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		t.Fatal("handler should not be called")
	}))

	req := httptest.NewRequest(http.MethodGet, "/", nil)
	req.Header.Set("Authorization", "Bearer bad-token")
	w := httptest.NewRecorder()
	handler.ServeHTTP(w, req)

	if w.Code != http.StatusUnauthorized {
		t.Errorf("status = %d, want 401", w.Code)
	}

	var body map[string]string
	json.NewDecoder(w.Body).Decode(&body)
	if body["code"] != "UNAUTHORIZED" {
		t.Errorf("code = %q", body["code"])
	}
}

func TestJWTMiddleware_MalformedHeader(t *testing.T) {
	middleware := JWTMiddleware(mockValidator(true, uuid.New(), "a@b.com"))
	handler := middleware(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		t.Fatal("handler should not be called")
	}))

	req := httptest.NewRequest(http.MethodGet, "/", nil)
	req.Header.Set("Authorization", "NotBearer token")
	w := httptest.NewRecorder()
	handler.ServeHTTP(w, req)

	if w.Code != http.StatusUnauthorized {
		t.Errorf("status = %d, want 401", w.Code)
	}
}
