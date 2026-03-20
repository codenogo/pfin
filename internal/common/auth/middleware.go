package auth

import (
	"net/http"
	"strings"

	"github.com/codenogo/pfin/internal/common/server"
	"github.com/codenogo/pfin/pkg/errs"
	"github.com/google/uuid"
)

// TokenValidator validates a JWT access token and returns claims.
type TokenValidator func(tokenStr string) (userID uuid.UUID, email string, err error)

// JWTMiddleware validates the Authorization: Bearer <token> header
// and injects UserContext into the request context.
func JWTMiddleware(validate TokenValidator) func(http.Handler) http.Handler {
	return func(next http.Handler) http.Handler {
		return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			authHeader := r.Header.Get("Authorization")
			if authHeader == "" {
				server.Error(w, errs.Unauthorized())
				return
			}

			parts := strings.SplitN(authHeader, " ", 2)
			if len(parts) != 2 || !strings.EqualFold(parts[0], "bearer") {
				server.Error(w, errs.Unauthorized())
				return
			}

			userID, email, err := validate(parts[1])
			if err != nil {
				server.Error(w, errs.Unauthorized())
				return
			}

			uc := &UserContext{UserID: userID, Email: email}
			ctx := ContextWithUser(r.Context(), uc)
			next.ServeHTTP(w, r.WithContext(ctx))
		})
	}
}
