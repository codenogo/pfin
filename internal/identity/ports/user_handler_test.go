package ports

import (
	"bytes"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/codenogo/pfin/internal/common/auth"
	"github.com/codenogo/pfin/internal/identity/domain/user"
	"github.com/google/uuid"
)

func TestHandleGetProfile_Success(t *testing.T) {
	userRepo := newMockUserRepo()

	// Create a user directly in the repo
	hash, _ := user.HashPassword("MyP@ss1!")
	u, _ := user.NewUser("profile@test.com", hash, "Profile User")
	userRepo.Create(nil, u)

	handler := NewUserHandler(userRepo)
	router := handler.Routes()

	req := httptest.NewRequest(http.MethodGet, "/me", nil)
	// Inject user context (simulating JWT middleware)
	ctx := auth.ContextWithUser(req.Context(), &auth.UserContext{
		UserID: u.ID,
		Email:  u.Email,
	})
	req = req.WithContext(ctx)
	w := httptest.NewRecorder()

	router.ServeHTTP(w, req)

	if w.Code != http.StatusOK {
		t.Errorf("status = %d, want 200. Body: %s", w.Code, w.Body.String())
	}

	var resp map[string]any
	json.NewDecoder(w.Body).Decode(&resp)
	if resp["email"] != "profile@test.com" {
		t.Errorf("email = %v", resp["email"])
	}
	if resp["display_name"] != "Profile User" {
		t.Errorf("display_name = %v", resp["display_name"])
	}
}

func TestHandleGetProfile_NoContext(t *testing.T) {
	userRepo := newMockUserRepo()
	handler := NewUserHandler(userRepo)
	router := handler.Routes()

	req := httptest.NewRequest(http.MethodGet, "/me", nil)
	w := httptest.NewRecorder()
	router.ServeHTTP(w, req)

	// Should return 500 since no user context (middleware would normally block this)
	if w.Code != http.StatusInternalServerError {
		t.Errorf("status = %d, want 500 (no user context)", w.Code)
	}
}

func TestHandleUpdateProfile_Success(t *testing.T) {
	userRepo := newMockUserRepo()

	hash, _ := user.HashPassword("MyP@ss1!")
	u, _ := user.NewUser("update@test.com", hash, "Old Name")
	userRepo.Create(nil, u)

	handler := NewUserHandler(userRepo)
	router := handler.Routes()

	body, _ := json.Marshal(map[string]string{"display_name": "New Name"})
	req := httptest.NewRequest(http.MethodPatch, "/me", bytes.NewReader(body))
	req.Header.Set("Content-Type", "application/json")
	ctx := auth.ContextWithUser(req.Context(), &auth.UserContext{
		UserID: u.ID,
		Email:  u.Email,
	})
	req = req.WithContext(ctx)
	w := httptest.NewRecorder()

	router.ServeHTTP(w, req)

	if w.Code != http.StatusOK {
		t.Errorf("status = %d, want 200. Body: %s", w.Code, w.Body.String())
	}

	var resp map[string]any
	json.NewDecoder(w.Body).Decode(&resp)
	if resp["display_name"] != "New Name" {
		t.Errorf("display_name = %v, want New Name", resp["display_name"])
	}
}

func TestHandleUpdateProfile_EmptyName(t *testing.T) {
	userRepo := newMockUserRepo()

	hash, _ := user.HashPassword("MyP@ss1!")
	u, _ := user.NewUser("empty@test.com", hash, "User")
	userRepo.Create(nil, u)

	handler := NewUserHandler(userRepo)
	router := handler.Routes()

	body, _ := json.Marshal(map[string]string{"display_name": ""})
	req := httptest.NewRequest(http.MethodPatch, "/me", bytes.NewReader(body))
	req.Header.Set("Content-Type", "application/json")
	ctx := auth.ContextWithUser(req.Context(), &auth.UserContext{
		UserID: u.ID,
		Email:  u.Email,
	})
	req = req.WithContext(ctx)
	w := httptest.NewRecorder()

	router.ServeHTTP(w, req)

	// Domain layer rejects empty name
	if w.Code != http.StatusInternalServerError {
		t.Errorf("status = %d, want 500 (domain error not wrapped as DomainError)", w.Code)
	}
}

func TestHandleGetProfile_UserNotFound(t *testing.T) {
	userRepo := newMockUserRepo()
	handler := NewUserHandler(userRepo)
	router := handler.Routes()

	req := httptest.NewRequest(http.MethodGet, "/me", nil)
	ctx := auth.ContextWithUser(req.Context(), &auth.UserContext{
		UserID: uuid.New(), // non-existent user
		Email:  "ghost@test.com",
	})
	req = req.WithContext(ctx)
	w := httptest.NewRecorder()

	router.ServeHTTP(w, req)

	if w.Code != http.StatusNotFound {
		t.Errorf("status = %d, want 404", w.Code)
	}
}
