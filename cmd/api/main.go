package main

import (
	"context"
	"fmt"
	"log/slog"
	"net/http"
	"os"
	"os/signal"
	"syscall"
	"time"

	"github.com/go-chi/chi/v5"
	"github.com/google/uuid"
	"github.com/jackc/pgx/v5/pgxpool"

	"github.com/codenogo/pfin/internal/common/auth"
	"github.com/codenogo/pfin/internal/common/event"
	"github.com/codenogo/pfin/internal/common/server"
	"github.com/codenogo/pfin/internal/config"
	identityPorts "github.com/codenogo/pfin/internal/identity/ports"
	identityService "github.com/codenogo/pfin/internal/identity/service"
)

func main() {
	if err := run(); err != nil {
		slog.Error("application failed", "error", err)
		os.Exit(1)
	}
}

func run() error {
	// Load config
	cfg := config.Load()

	// Setup logging
	var handler slog.Handler
	if cfg.IsProd() {
		handler = slog.NewJSONHandler(os.Stdout, &slog.HandlerOptions{Level: slog.LevelInfo})
	} else {
		handler = slog.NewTextHandler(os.Stdout, &slog.HandlerOptions{Level: slog.LevelDebug})
	}
	slog.SetDefault(slog.New(handler))

	// Connect to PostgreSQL
	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()

	pool, err := pgxpool.New(ctx, cfg.DatabaseURL)
	if err != nil {
		return fmt.Errorf("connect to database: %w", err)
	}
	defer pool.Close()

	if err := pool.Ping(ctx); err != nil {
		slog.Warn("database not reachable at startup", "error", err)
	} else {
		slog.Info("connected to database")
	}

	// Create event bus
	syncBus := event.NewBus()
	asyncBus := event.NewAsyncBus(2, 100)
	publisher := event.NewCompositePublisher(syncBus, asyncBus)
	defer publisher.Close()

	// ── Identity Context ──
	accessTTL := 15 * time.Minute
	refreshTTL := 14 * 24 * time.Hour
	identityApp := identityService.NewApplication(pool, publisher, cfg.JWTSecret, accessTTL, refreshTTL)

	authHandler := identityPorts.NewAuthHandler(
		identityApp.Register, identityApp.Authenticate,
		identityApp.Refresh, identityApp.Logout, refreshTTL,
	)
	userHandler := identityPorts.NewUserHandler(
		identityApp.UserRepo(),
	)

	// JWT validator function for middleware
	tokenIssuer := identityApp.TokenIssuer()
	jwtValidator := auth.TokenValidator(func(tokenStr string) (uuid.UUID, string, error) {
		claims, err := tokenIssuer.ValidateAccessToken(tokenStr)
		if err != nil {
			return uuid.Nil, "", err
		}
		return claims.UserID, claims.Email, nil
	})

	// Build router
	r := chi.NewRouter()

	// Global middleware
	r.Use(server.RequestID)
	r.Use(server.StructuredLogger)
	r.Use(server.Recovery)
	r.Use(server.CORS(cfg.CORSOrigins))

	// Health endpoint
	r.Get("/health", server.HealthHandler(pool))

	// Public auth routes
	r.Mount("/auth", authHandler.Routes())

	// Protected routes (JWT required)
	r.Group(func(r chi.Router) {
		r.Use(auth.JWTMiddleware(jwtValidator))
		r.Mount("/users", userHandler.Routes())
	})

	// Start server
	srv := &http.Server{
		Addr:         ":" + cfg.Port,
		Handler:      r,
		ReadTimeout:  15 * time.Second,
		WriteTimeout: 15 * time.Second,
		IdleTimeout:  60 * time.Second,
	}

	// Graceful shutdown
	errCh := make(chan error, 1)
	go func() {
		slog.Info("server starting", "port", cfg.Port, "env", cfg.Env)
		errCh <- srv.ListenAndServe()
	}()

	quit := make(chan os.Signal, 1)
	signal.Notify(quit, syscall.SIGINT, syscall.SIGTERM)

	select {
	case sig := <-quit:
		slog.Info("shutdown signal received", "signal", sig)
	case err := <-errCh:
		if err != nil && err != http.ErrServerClosed {
			return fmt.Errorf("server error: %w", err)
		}
	}

	shutdownCtx, shutdownCancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer shutdownCancel()

	if err := srv.Shutdown(shutdownCtx); err != nil {
		return fmt.Errorf("graceful shutdown failed: %w", err)
	}

	slog.Info("server stopped gracefully")
	return nil
}
