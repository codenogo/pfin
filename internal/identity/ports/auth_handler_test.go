package ports

import (
	"bytes"
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"

	"github.com/codenogo/pfin/internal/common/event"
	"github.com/codenogo/pfin/internal/identity/adapters"
	"github.com/codenogo/pfin/internal/identity/app/command"
	"github.com/codenogo/pfin/internal/identity/domain/session"
	"github.com/codenogo/pfin/internal/identity/domain/user"
	"github.com/codenogo/pfin/pkg/errs"
	"github.com/google/uuid"
)

// --- mock repos (same pattern as command tests) ---

type mockUserRepo struct {
	users map[string]*user.User
}

func newMockUserRepo() *mockUserRepo {
	return &mockUserRepo{users: make(map[string]*user.User)}
}

func (m *mockUserRepo) Create(ctx context.Context, u *user.User) error {
	if _, exists := m.users[u.Email]; exists {
		return errs.Conflict("email already registered")
	}
	m.users[u.Email] = u
	return nil
}

func (m *mockUserRepo) GetByID(ctx context.Context, id uuid.UUID) (*user.User, error) {
	for _, u := range m.users {
		if u.ID == id {
			return u, nil
		}
	}
	return nil, errs.NotFound("user", id.String())
}

func (m *mockUserRepo) GetByEmail(ctx context.Context, email string) (*user.User, error) {
	u, ok := m.users[email]
	if !ok {
		return nil, errs.NotFound("user", email)
	}
	return u, nil
}

func (m *mockUserRepo) Update(ctx context.Context, u *user.User) error {
	m.users[u.Email] = u
	return nil
}

type mockSessionRepo struct {
	tokens map[string]*session.RefreshToken
}

func newMockSessionRepo() *mockSessionRepo {
	return &mockSessionRepo{tokens: make(map[string]*session.RefreshToken)}
}

func (m *mockSessionRepo) Create(ctx context.Context, token *session.RefreshToken) error {
	m.tokens[token.TokenHash] = token
	return nil
}

func (m *mockSessionRepo) GetByTokenHash(ctx context.Context, tokenHash string) (*session.RefreshToken, error) {
	t, ok := m.tokens[tokenHash]
	if !ok {
		return nil, errs.NotFound("token", "***")
	}
	return t, nil
}

func (m *mockSessionRepo) RevokeByID(ctx context.Context, id uuid.UUID) error {
	for _, t := range m.tokens {
		if t.ID == id {
			t.Revoked = true
		}
	}
	return nil
}

func (m *mockSessionRepo) RevokeAllForUser(ctx context.Context, userID uuid.UUID) error {
	for _, t := range m.tokens {
		if t.UserID == userID {
			t.Revoked = true
		}
	}
	return nil
}

func setupAuthHandler() (*AuthHandler, *mockUserRepo) {
	userRepo := newMockUserRepo()
	sessionRepo := newMockSessionRepo()
	issuer := adapters.NewTokenIssuer("test-secret-32-chars-long!!!", 15*time.Minute)
	bus := event.NewBus()
	refreshTTL := 14 * 24 * time.Hour

	register := command.NewRegisterHandler(userRepo, bus)
	authenticate := command.NewAuthenticateHandler(userRepo, sessionRepo, issuer, refreshTTL)
	refresh := command.NewRefreshHandler(userRepo, sessionRepo, issuer, refreshTTL)
	logout := command.NewLogoutHandler(sessionRepo)

	handler := NewAuthHandler(register, authenticate, refresh, logout, refreshTTL)
	return handler, userRepo
}

func TestHandleRegister_Success(t *testing.T) {
	handler, _ := setupAuthHandler()
	router := handler.Routes()

	body, _ := json.Marshal(map[string]string{
		"email": "test@example.com", "password": "MyP@ss1!", "display_name": "Test",
	})
	req := httptest.NewRequest(http.MethodPost, "/register", bytes.NewReader(body))
	req.Header.Set("Content-Type", "application/json")
	w := httptest.NewRecorder()

	router.ServeHTTP(w, req)

	if w.Code != http.StatusCreated {
		t.Errorf("status = %d, want 201. Body: %s", w.Code, w.Body.String())
	}
	var resp map[string]any
	json.NewDecoder(w.Body).Decode(&resp)
	if resp["email"] != "test@example.com" {
		t.Errorf("email = %v", resp["email"])
	}
}

func TestHandleRegister_InvalidPassword(t *testing.T) {
	handler, _ := setupAuthHandler()
	router := handler.Routes()

	body, _ := json.Marshal(map[string]string{
		"email": "test@example.com", "password": "weak", "display_name": "Test",
	})
	req := httptest.NewRequest(http.MethodPost, "/register", bytes.NewReader(body))
	req.Header.Set("Content-Type", "application/json")
	w := httptest.NewRecorder()

	router.ServeHTTP(w, req)

	if w.Code != http.StatusBadRequest {
		t.Errorf("status = %d, want 400", w.Code)
	}
}

func TestHandleRegister_DuplicateEmail(t *testing.T) {
	handler, _ := setupAuthHandler()
	router := handler.Routes()

	body, _ := json.Marshal(map[string]string{
		"email": "dup@example.com", "password": "MyP@ss1!", "display_name": "User1",
	})
	req := httptest.NewRequest(http.MethodPost, "/register", bytes.NewReader(body))
	req.Header.Set("Content-Type", "application/json")
	w := httptest.NewRecorder()
	router.ServeHTTP(w, req)

	// Second registration with same email
	req2 := httptest.NewRequest(http.MethodPost, "/register", bytes.NewReader(body))
	req2.Header.Set("Content-Type", "application/json")
	w2 := httptest.NewRecorder()
	router.ServeHTTP(w2, req2)

	if w2.Code != http.StatusConflict {
		t.Errorf("status = %d, want 409", w2.Code)
	}
}

func TestHandleLogin_Success(t *testing.T) {
	handler, _ := setupAuthHandler()
	router := handler.Routes()

	// Register first
	regBody, _ := json.Marshal(map[string]string{
		"email": "login@example.com", "password": "MyP@ss1!", "display_name": "Login",
	})
	regReq := httptest.NewRequest(http.MethodPost, "/register", bytes.NewReader(regBody))
	regReq.Header.Set("Content-Type", "application/json")
	router.ServeHTTP(httptest.NewRecorder(), regReq)

	// Login
	loginBody, _ := json.Marshal(map[string]string{
		"email": "login@example.com", "password": "MyP@ss1!",
	})
	req := httptest.NewRequest(http.MethodPost, "/login", bytes.NewReader(loginBody))
	req.Header.Set("Content-Type", "application/json")
	w := httptest.NewRecorder()
	router.ServeHTTP(w, req)

	if w.Code != http.StatusOK {
		t.Errorf("status = %d, want 200. Body: %s", w.Code, w.Body.String())
	}

	var resp map[string]string
	json.NewDecoder(w.Body).Decode(&resp)
	if resp["access_token"] == "" {
		t.Error("access_token should not be empty")
	}

	// Check refresh cookie was set
	cookies := w.Result().Cookies()
	found := false
	for _, c := range cookies {
		if c.Name == "pfin_refresh_token" {
			found = true
			if !c.HttpOnly {
				t.Error("refresh cookie should be HttpOnly")
			}
			if c.SameSite != http.SameSiteStrictMode {
				t.Error("refresh cookie should be SameSite=Strict")
			}
		}
	}
	if !found {
		t.Error("refresh cookie should be set on login")
	}
}

func TestHandleLogin_WrongPassword(t *testing.T) {
	handler, _ := setupAuthHandler()
	router := handler.Routes()

	// Register
	regBody, _ := json.Marshal(map[string]string{
		"email": "wrong@example.com", "password": "MyP@ss1!", "display_name": "User",
	})
	regReq := httptest.NewRequest(http.MethodPost, "/register", bytes.NewReader(regBody))
	regReq.Header.Set("Content-Type", "application/json")
	router.ServeHTTP(httptest.NewRecorder(), regReq)

	// Login with wrong password
	loginBody, _ := json.Marshal(map[string]string{
		"email": "wrong@example.com", "password": "WrongP@ss1!",
	})
	req := httptest.NewRequest(http.MethodPost, "/login", bytes.NewReader(loginBody))
	req.Header.Set("Content-Type", "application/json")
	w := httptest.NewRecorder()
	router.ServeHTTP(w, req)

	if w.Code != http.StatusUnauthorized {
		t.Errorf("status = %d, want 401", w.Code)
	}
}

func TestHandleRefresh_NoCookie(t *testing.T) {
	handler, _ := setupAuthHandler()
	router := handler.Routes()

	req := httptest.NewRequest(http.MethodPost, "/refresh", nil)
	w := httptest.NewRecorder()
	router.ServeHTTP(w, req)

	if w.Code != http.StatusUnauthorized {
		t.Errorf("status = %d, want 401", w.Code)
	}
}

func TestHandleLogout_NoCookie(t *testing.T) {
	handler, _ := setupAuthHandler()
	router := handler.Routes()

	req := httptest.NewRequest(http.MethodPost, "/logout", nil)
	w := httptest.NewRecorder()
	router.ServeHTTP(w, req)

	if w.Code != http.StatusNoContent {
		t.Errorf("status = %d, want 204 (idempotent logout)", w.Code)
	}
}

func TestHandleRegister_InvalidJSON(t *testing.T) {
	handler, _ := setupAuthHandler()
	router := handler.Routes()

	req := httptest.NewRequest(http.MethodPost, "/register", bytes.NewReader([]byte("not json")))
	req.Header.Set("Content-Type", "application/json")
	w := httptest.NewRecorder()
	router.ServeHTTP(w, req)

	if w.Code != http.StatusBadRequest {
		t.Errorf("status = %d, want 400", w.Code)
	}
}
