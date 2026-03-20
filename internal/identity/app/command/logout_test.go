package command

import (
	"context"
	"testing"
	"time"

	"github.com/codenogo/pfin/internal/common/event"
	"github.com/codenogo/pfin/internal/identity/adapters"
	"github.com/codenogo/pfin/internal/identity/domain/session"
)

func TestLogout_Success(t *testing.T) {
	userRepo := newMockUserRepo()
	sessionRepo := newMockSessionRepo()
	issuer := adapters.NewTokenIssuer("secret", 15*time.Minute)
	bus := event.NewBus()
	refreshTTL := 14 * 24 * time.Hour

	// Register + login
	regHandler := NewRegisterHandler(userRepo, bus)
	regHandler.Handle(context.Background(), RegisterCmd{
		Email: "logout@test.com", Password: "MyP@ss1!", DisplayName: "User",
	})
	authHandler := NewAuthenticateHandler(userRepo, sessionRepo, issuer, refreshTTL)
	pair, _ := authHandler.Handle(context.Background(), AuthenticateCmd{
		Email: "logout@test.com", Password: "MyP@ss1!",
	})

	// Logout
	logoutHandler := NewLogoutHandler(sessionRepo)
	err := logoutHandler.Handle(context.Background(), LogoutCmd{
		RawToken: pair.RefreshToken,
	})
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}

	// Verify token is revoked — refresh should fail
	tokenHash := session.HashToken(pair.RefreshToken)
	rt, _ := sessionRepo.GetByTokenHash(context.Background(), tokenHash)
	if rt != nil && !rt.Revoked {
		t.Error("token should be revoked after logout")
	}
}

func TestLogout_NonexistentToken(t *testing.T) {
	sessionRepo := newMockSessionRepo()
	handler := NewLogoutHandler(sessionRepo)

	// Logout with a token that doesn't exist — should succeed (idempotent)
	err := handler.Handle(context.Background(), LogoutCmd{
		RawToken: "nonexistent-token",
	})
	if err != nil {
		t.Errorf("logout with nonexistent token should succeed, got: %v", err)
	}
}
