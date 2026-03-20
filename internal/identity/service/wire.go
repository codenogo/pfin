package service

import (
	"time"

	"github.com/jackc/pgx/v5/pgxpool"

	"github.com/codenogo/pfin/internal/common/event"
	"github.com/codenogo/pfin/internal/identity/adapters"
	"github.com/codenogo/pfin/internal/identity/app/command"
)

// Application holds all Identity context command handlers.
type Application struct {
	Register     *command.RegisterHandler
	Authenticate *command.AuthenticateHandler
	Refresh      *command.RefreshHandler
	Logout       *command.LogoutHandler
	userRepo     *adapters.PostgresUserRepo
	tokenIssuer  *adapters.TokenIssuer
}

// UserRepo returns the user repository (for user profile handler).
func (a *Application) UserRepo() *adapters.PostgresUserRepo {
	return a.userRepo
}

// TokenIssuer returns the JWT token issuer (for JWT middleware validator).
func (a *Application) TokenIssuer() *adapters.TokenIssuer {
	return a.tokenIssuer
}

// NewApplication wires all Identity context dependencies.
func NewApplication(
	pool *pgxpool.Pool,
	publisher event.Publisher,
	jwtSecret string,
	accessTTL time.Duration,
	refreshTTL time.Duration,
) *Application {
	userRepo := adapters.NewPostgresUserRepo(pool)
	sessionRepo := adapters.NewPostgresSessionRepo(pool)
	issuer := adapters.NewTokenIssuer(jwtSecret, accessTTL)

	return &Application{
		Register:     command.NewRegisterHandler(userRepo, publisher),
		Authenticate: command.NewAuthenticateHandler(userRepo, sessionRepo, issuer, refreshTTL),
		Refresh:      command.NewRefreshHandler(userRepo, sessionRepo, issuer, refreshTTL),
		Logout:       command.NewLogoutHandler(sessionRepo),
		userRepo:     userRepo,
		tokenIssuer:  issuer,
	}
}
