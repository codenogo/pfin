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

func TestRefresh_Success(t *testing.T) {
	userRepo := newMockUserRepo()
	sessionRepo := newMockSessionRepo()
	issuer := adapters.NewTokenIssuer("test-secret-32-chars!!!", 15*time.Minute)
	bus := event.NewBus()
	refreshTTL := 14 * 24 * time.Hour

	// Register + login to get a refresh token
	regHandler := NewRegisterHandler(userRepo, bus)
	regHandler.Handle(context.Background(), RegisterCmd{
		Email: "refresh@test.com", Password: "MyP@ss1!", DisplayName: "Refresh User",
	})

	authHandler := NewAuthenticateHandler(userRepo, sessionRepo, issuer, refreshTTL)
	pair, _ := authHandler.Handle(context.Background(), AuthenticateCmd{
		Email: "refresh@test.com", Password: "MyP@ss1!",
	})

	// Now refresh
	refreshHandler := NewRefreshHandler(userRepo, sessionRepo, issuer, refreshTTL)
	newPair, err := refreshHandler.Handle(context.Background(), RefreshCmd{
		RawToken: pair.RefreshToken,
	})
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if newPair.AccessToken == "" {
		t.Error("new access token should not be empty")
	}
	if newPair.RefreshToken == "" {
		t.Error("new refresh token should not be empty")
	}
	if newPair.RefreshToken == pair.RefreshToken {
		t.Error("refresh token should be rotated (different from original)")
	}
}

func TestRefresh_InvalidToken(t *testing.T) {
	userRepo := newMockUserRepo()
	sessionRepo := newMockSessionRepo()
	issuer := adapters.NewTokenIssuer("secret", 15*time.Minute)

	handler := NewRefreshHandler(userRepo, sessionRepo, issuer, 14*24*time.Hour)
	_, err := handler.Handle(context.Background(), RefreshCmd{
		RawToken: "nonexistent-token",
	})
	if err == nil {
		t.Error("expected unauthorized error for invalid token")
	}
}

func TestRefresh_ExpiredToken(t *testing.T) {
	userRepo := newMockUserRepo()
	sessionRepo := newMockSessionRepo()
	issuer := adapters.NewTokenIssuer("secret", 15*time.Minute)
	bus := event.NewBus()

	// Register a user
	regHandler := NewRegisterHandler(userRepo, bus)
	regHandler.Handle(context.Background(), RegisterCmd{
		Email: "expired@test.com", Password: "MyP@ss1!", DisplayName: "User",
	})

	// Manually create an expired refresh token
	raw, hash, _ := session.GenerateToken()
	expiredToken := session.NewRefreshToken(uuid.New(), hash, -1*time.Hour) // already expired
	// Find the user to get their ID
	u, _ := userRepo.GetByEmail(context.Background(), "expired@test.com")
	expiredToken.UserID = u.ID
	sessionRepo.Create(context.Background(), expiredToken)

	handler := NewRefreshHandler(userRepo, sessionRepo, issuer, 14*24*time.Hour)
	_, err := handler.Handle(context.Background(), RefreshCmd{
		RawToken: raw,
	})
	if err == nil {
		t.Error("expected unauthorized error for expired token")
	}
}

func TestRefresh_RevokedToken(t *testing.T) {
	userRepo := newMockUserRepo()
	sessionRepo := newMockSessionRepo()
	issuer := adapters.NewTokenIssuer("secret", 15*time.Minute)
	bus := event.NewBus()

	regHandler := NewRegisterHandler(userRepo, bus)
	regHandler.Handle(context.Background(), RegisterCmd{
		Email: "revoked@test.com", Password: "MyP@ss1!", DisplayName: "User",
	})

	// Create a token and then revoke it
	raw, hash, _ := session.GenerateToken()
	u, _ := userRepo.GetByEmail(context.Background(), "revoked@test.com")
	rt := session.NewRefreshToken(u.ID, hash, 14*24*time.Hour)
	sessionRepo.Create(context.Background(), rt)
	sessionRepo.RevokeByID(context.Background(), rt.ID)

	handler := NewRefreshHandler(userRepo, sessionRepo, issuer, 14*24*time.Hour)
	_, err := handler.Handle(context.Background(), RefreshCmd{
		RawToken: raw,
	})
	if err == nil {
		t.Error("expected unauthorized error for revoked token")
	}
}
