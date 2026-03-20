package ports

import (
	"encoding/json"
	"net/http"
	"time"

	"github.com/go-chi/chi/v5"

	"github.com/codenogo/pfin/internal/common/server"
	"github.com/codenogo/pfin/internal/identity/app/command"
)

const (
	refreshCookieName = "pfin_refresh_token"
	refreshCookiePath = "/auth"
)

// AuthHandler handles authentication HTTP endpoints.
type AuthHandler struct {
	register     *command.RegisterHandler
	authenticate *command.AuthenticateHandler
	refresh      *command.RefreshHandler
	logout       *command.LogoutHandler
	refreshTTL   time.Duration
}

// NewAuthHandler creates an AuthHandler.
func NewAuthHandler(
	register *command.RegisterHandler,
	authenticate *command.AuthenticateHandler,
	refresh *command.RefreshHandler,
	logout *command.LogoutHandler,
	refreshTTL time.Duration,
) *AuthHandler {
	return &AuthHandler{
		register:     register,
		authenticate: authenticate,
		refresh:      refresh,
		logout:       logout,
		refreshTTL:   refreshTTL,
	}
}

// Routes returns a chi router with auth routes mounted.
func (h *AuthHandler) Routes() chi.Router {
	r := chi.NewRouter()
	r.Post("/register", h.handleRegister)
	r.Post("/login", h.handleLogin)
	r.Post("/refresh", h.handleRefresh)
	r.Post("/logout", h.handleLogout)
	return r
}

func (h *AuthHandler) handleRegister(w http.ResponseWriter, r *http.Request) {
	var req struct {
		Email       string `json:"email"`
		Password    string `json:"password"`
		DisplayName string `json:"display_name"`
	}
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		server.JSON(w, http.StatusBadRequest, map[string]string{
			"code": "VALIDATION_ERROR", "message": "invalid request body",
		})
		return
	}

	u, err := h.register.Handle(r.Context(), command.RegisterCmd{
		Email:       req.Email,
		Password:    req.Password,
		DisplayName: req.DisplayName,
	})
	if err != nil {
		server.Error(w, err)
		return
	}

	server.JSON(w, http.StatusCreated, map[string]any{
		"id":           u.ID,
		"email":        u.Email,
		"display_name": u.DisplayName,
	})
}

func (h *AuthHandler) handleLogin(w http.ResponseWriter, r *http.Request) {
	var req struct {
		Email    string `json:"email"`
		Password string `json:"password"`
	}
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		server.JSON(w, http.StatusBadRequest, map[string]string{
			"code": "VALIDATION_ERROR", "message": "invalid request body",
		})
		return
	}

	pair, err := h.authenticate.Handle(r.Context(), command.AuthenticateCmd{
		Email:    req.Email,
		Password: req.Password,
	})
	if err != nil {
		server.Error(w, err)
		return
	}

	h.setRefreshCookie(w, pair.RefreshToken)
	server.JSON(w, http.StatusOK, map[string]string{
		"access_token": pair.AccessToken,
	})
}

func (h *AuthHandler) handleRefresh(w http.ResponseWriter, r *http.Request) {
	cookie, err := r.Cookie(refreshCookieName)
	if err != nil {
		server.JSON(w, http.StatusUnauthorized, map[string]string{
			"code": "UNAUTHORIZED", "message": "refresh token not found",
		})
		return
	}

	pair, err := h.refresh.Handle(r.Context(), command.RefreshCmd{
		RawToken: cookie.Value,
	})
	if err != nil {
		h.clearRefreshCookie(w)
		server.Error(w, err)
		return
	}

	h.setRefreshCookie(w, pair.RefreshToken)
	server.JSON(w, http.StatusOK, map[string]string{
		"access_token": pair.AccessToken,
	})
}

func (h *AuthHandler) handleLogout(w http.ResponseWriter, r *http.Request) {
	cookie, err := r.Cookie(refreshCookieName)
	if err != nil {
		// No cookie — already logged out
		w.WriteHeader(http.StatusNoContent)
		return
	}

	h.logout.Handle(r.Context(), command.LogoutCmd{
		RawToken: cookie.Value,
	})

	h.clearRefreshCookie(w)
	w.WriteHeader(http.StatusNoContent)
}

func (h *AuthHandler) setRefreshCookie(w http.ResponseWriter, token string) {
	http.SetCookie(w, &http.Cookie{
		Name:     refreshCookieName,
		Value:    token,
		Path:     refreshCookiePath,
		MaxAge:   int(h.refreshTTL.Seconds()),
		HttpOnly: true,
		Secure:   true,
		SameSite: http.SameSiteStrictMode,
	})
}

func (h *AuthHandler) clearRefreshCookie(w http.ResponseWriter) {
	http.SetCookie(w, &http.Cookie{
		Name:     refreshCookieName,
		Value:    "",
		Path:     refreshCookiePath,
		MaxAge:   -1,
		HttpOnly: true,
		Secure:   true,
		SameSite: http.SameSiteStrictMode,
	})
}
