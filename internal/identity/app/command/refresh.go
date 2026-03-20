package command

import (
	"context"
	"time"

	"github.com/codenogo/pfin/internal/identity/adapters"
	"github.com/codenogo/pfin/internal/identity/domain/session"
	"github.com/codenogo/pfin/internal/identity/domain/user"
	"github.com/codenogo/pfin/pkg/errs"
)

// RefreshCmd is the input for token refresh.
type RefreshCmd struct {
	RawToken string // the raw refresh token from the cookie
}

// RefreshHandler handles token rotation.
type RefreshHandler struct {
	users      user.Repository
	sessions   session.Repository
	issuer     *adapters.TokenIssuer
	refreshTTL time.Duration
}

// NewRefreshHandler creates a RefreshHandler.
func NewRefreshHandler(
	users user.Repository,
	sessions session.Repository,
	issuer *adapters.TokenIssuer,
	refreshTTL time.Duration,
) *RefreshHandler {
	return &RefreshHandler{
		users:      users,
		sessions:   sessions,
		issuer:     issuer,
		refreshTTL: refreshTTL,
	}
}

// Handle processes a token refresh command with rotation.
func (h *RefreshHandler) Handle(ctx context.Context, cmd RefreshCmd) (*TokenPair, error) {
	tokenHash := session.HashToken(cmd.RawToken)

	existing, err := h.sessions.GetByTokenHash(ctx, tokenHash)
	if err != nil {
		return nil, errs.New(errs.CodeUnauthorized, "invalid refresh token")
	}

	if !existing.IsValid() {
		// Token reuse detected or expired — revoke all tokens for this user
		h.sessions.RevokeAllForUser(ctx, existing.UserID)
		return nil, errs.New(errs.CodeUnauthorized, "refresh token expired or revoked")
	}

	// Revoke old token (single-use rotation)
	if err := h.sessions.RevokeByID(ctx, existing.ID); err != nil {
		return nil, errs.Wrap(errs.CodeInternal, "failed to revoke old token", err)
	}

	// Get user for access token claims
	u, err := h.users.GetByID(ctx, existing.UserID)
	if err != nil {
		return nil, errs.Wrap(errs.CodeInternal, "failed to load user", err)
	}

	// Issue new token pair
	accessToken, err := h.issuer.IssueAccessToken(u.ID, u.Email)
	if err != nil {
		return nil, errs.Wrap(errs.CodeInternal, "failed to issue access token", err)
	}

	rawRefresh, hashRefresh, err := session.GenerateToken()
	if err != nil {
		return nil, errs.Wrap(errs.CodeInternal, "failed to generate refresh token", err)
	}

	rt := session.NewRefreshToken(u.ID, hashRefresh, h.refreshTTL)
	if err := h.sessions.Create(ctx, rt); err != nil {
		return nil, errs.Wrap(errs.CodeInternal, "failed to store new refresh token", err)
	}

	return &TokenPair{
		AccessToken:  accessToken,
		RefreshToken: rawRefresh,
	}, nil
}
