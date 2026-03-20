package auth

import (
	"context"
	"fmt"

	"github.com/google/uuid"
)

type contextKey string

const userContextKey contextKey = "user"

// UserContext holds authenticated user info extracted from JWT.
type UserContext struct {
	UserID uuid.UUID
	Email  string
}

// ContextWithUser stores UserContext in the request context.
func ContextWithUser(ctx context.Context, uc *UserContext) context.Context {
	return context.WithValue(ctx, userContextKey, uc)
}

// UserFromContext extracts UserContext from the request context.
func UserFromContext(ctx context.Context) (*UserContext, error) {
	uc, ok := ctx.Value(userContextKey).(*UserContext)
	if !ok || uc == nil {
		return nil, fmt.Errorf("user not found in context")
	}
	return uc, nil
}
