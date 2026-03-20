package command

import (
	"context"
	"time"

	"github.com/codenogo/pfin/internal/identity/adapters"
	"github.com/codenogo/pfin/internal/identity/domain/session"
	"github.com/codenogo/pfin/internal/identity/domain/user"
	"github.com/codenogo/pfin/pkg/errs"
)

// AuthenticateCmd is the input for login.
type AuthenticateCmd struct {
	Email    string
	Password string
}

// TokenPair holds the access and refresh tokens returned after authentication.
type TokenPair struct {
	AccessToken  string
	RefreshToken string // raw token (for cookie)
}

// AuthenticateHandler handles user login.
type AuthenticateHandler struct {
	users      user.Repository
	sessions   session.Repository
	issuer     *adapters.TokenIssuer
	refreshTTL time.Duration
}

// NewAuthenticateHandler creates an AuthenticateHandler.
func NewAuthenticateHandler(
	users user.Repository,
	sessions session.Repository,
	issuer *adapters.TokenIssuer,
	refreshTTL time.Duration,
) *AuthenticateHandler {
	return &AuthenticateHandler{
		users:      users,
		sessions:   sessions,
		issuer:     issuer,
		refreshTTL: refreshTTL,
	}
}

// Handle processes a login command.
func (h *AuthenticateHandler) Handle(ctx context.Context, cmd AuthenticateCmd) (*TokenPair, error) {
	u, err := h.users.GetByEmail(ctx, cmd.Email)
	if err != nil {
		return nil, errs.New(errs.CodeUnauthorized, "invalid email or password")
	}

	if err := user.CheckPassword(u.PasswordHash, cmd.Password); err != nil {
		return nil, errs.New(errs.CodeUnauthorized, "invalid email or password")
	}

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
		return nil, errs.Wrap(errs.CodeInternal, "failed to store refresh token", err)
	}

	return &TokenPair{
		AccessToken:  accessToken,
		RefreshToken: rawRefresh,
	}, nil
}
