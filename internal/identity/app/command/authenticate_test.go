package command

import (
	"context"
	"testing"
	"time"

	"github.com/codenogo/pfin/internal/common/event"
	"github.com/codenogo/pfin/internal/identity/adapters"
	"github.com/codenogo/pfin/internal/identity/domain/session"
	"github.com/google/uuid"
)

// mockSessionRepo is a test double for session.Repository.
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
		return nil, nil
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

func TestAuthenticate_Success(t *testing.T) {
	userRepo := newMockUserRepo()
	sessionRepo := newMockSessionRepo()
	issuer := adapters.NewTokenIssuer("test-secret-32-chars-long!!!", 15*time.Minute)
	bus := event.NewBus()

	// Register a user first
	regHandler := NewRegisterHandler(userRepo, bus)
	regHandler.Handle(context.Background(), RegisterCmd{
		Email: "login@test.com", Password: "MyP@ss1!", DisplayName: "Login Test",
	})

	authHandler := NewAuthenticateHandler(userRepo, sessionRepo, issuer, 14*24*time.Hour)
	pair, err := authHandler.Handle(context.Background(), AuthenticateCmd{
		Email: "login@test.com", Password: "MyP@ss1!",
	})
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if pair.AccessToken == "" {
		t.Error("access token should not be empty")
	}
	if pair.RefreshToken == "" {
		t.Error("refresh token should not be empty")
	}
	if len(sessionRepo.tokens) != 1 {
		t.Errorf("session repo should have 1 token, got %d", len(sessionRepo.tokens))
	}
}

func TestAuthenticate_WrongPassword(t *testing.T) {
	userRepo := newMockUserRepo()
	sessionRepo := newMockSessionRepo()
	issuer := adapters.NewTokenIssuer("secret", 15*time.Minute)
	bus := event.NewBus()

	regHandler := NewRegisterHandler(userRepo, bus)
	regHandler.Handle(context.Background(), RegisterCmd{
		Email: "a@b.com", Password: "MyP@ss1!", DisplayName: "User",
	})

	authHandler := NewAuthenticateHandler(userRepo, sessionRepo, issuer, 14*24*time.Hour)
	_, err := authHandler.Handle(context.Background(), AuthenticateCmd{
		Email: "a@b.com", Password: "WrongP@ss1!",
	})
	if err == nil {
		t.Error("expected unauthorized error")
	}
}

func TestAuthenticate_UserNotFound(t *testing.T) {
	userRepo := newMockUserRepo()
	sessionRepo := newMockSessionRepo()
	issuer := adapters.NewTokenIssuer("secret", 15*time.Minute)

	authHandler := NewAuthenticateHandler(userRepo, sessionRepo, issuer, 14*24*time.Hour)
	_, err := authHandler.Handle(context.Background(), AuthenticateCmd{
		Email: "nonexistent@test.com", Password: "MyP@ss1!",
	})
	if err == nil {
		t.Error("expected unauthorized error")
	}
}
