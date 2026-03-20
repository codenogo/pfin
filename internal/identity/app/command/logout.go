package command

import (
	"context"

	"github.com/codenogo/pfin/internal/identity/domain/session"
	"github.com/codenogo/pfin/pkg/errs"
)

// LogoutCmd is the input for logout.
type LogoutCmd struct {
	RawToken string // the raw refresh token from the cookie
}

// LogoutHandler handles logout by revoking the refresh token.
type LogoutHandler struct {
	sessions session.Repository
}

// NewLogoutHandler creates a LogoutHandler.
func NewLogoutHandler(sessions session.Repository) *LogoutHandler {
	return &LogoutHandler{sessions: sessions}
}

// Handle processes a logout command.
func (h *LogoutHandler) Handle(ctx context.Context, cmd LogoutCmd) error {
	tokenHash := session.HashToken(cmd.RawToken)

	existing, err := h.sessions.GetByTokenHash(ctx, tokenHash)
	if err != nil || existing == nil {
		// Token not found — already logged out, treat as success
		return nil
	}

	if err := h.sessions.RevokeByID(ctx, existing.ID); err != nil {
		return errs.Wrap(errs.CodeInternal, "failed to revoke token", err)
	}

	return nil
}
