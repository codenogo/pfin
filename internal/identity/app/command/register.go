package command

import (
	"context"
	"time"

	"github.com/codenogo/pfin/internal/common/event"
	"github.com/codenogo/pfin/internal/identity/domain/user"
	"github.com/codenogo/pfin/pkg/errs"
)

// RegisterCmd is the input for user registration.
type RegisterCmd struct {
	Email       string
	Password    string
	DisplayName string
}

// RegisterHandler handles user registration.
type RegisterHandler struct {
	users  user.Repository
	events event.Publisher
}

// NewRegisterHandler creates a RegisterHandler.
func NewRegisterHandler(users user.Repository, events event.Publisher) *RegisterHandler {
	return &RegisterHandler{users: users, events: events}
}

// Handle processes a registration command.
func (h *RegisterHandler) Handle(ctx context.Context, cmd RegisterCmd) (*user.User, error) {
	if err := user.ValidatePassword(cmd.Password); err != nil {
		return nil, errs.Wrap(errs.CodeValidation, err.Error(), err)
	}

	hash, err := user.HashPassword(cmd.Password)
	if err != nil {
		return nil, errs.Wrap(errs.CodeInternal, "failed to hash password", err)
	}

	u, err := user.NewUser(cmd.Email, hash, cmd.DisplayName)
	if err != nil {
		return nil, errs.Wrap(errs.CodeValidation, err.Error(), err)
	}

	if err := h.users.Create(ctx, u); err != nil {
		return nil, err // repo returns DomainError for conflicts
	}

	h.events.Publish(ctx, user.UserRegistered{
		UserID:    u.ID,
		Email:     u.Email,
		Timestamp: time.Now(),
	})

	return u, nil
}
