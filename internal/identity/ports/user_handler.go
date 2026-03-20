package ports

import (
	"encoding/json"
	"net/http"

	"github.com/go-chi/chi/v5"

	"github.com/codenogo/pfin/internal/common/auth"
	"github.com/codenogo/pfin/internal/common/server"
	"github.com/codenogo/pfin/internal/identity/domain/user"
)

// UserHandler handles user profile HTTP endpoints.
type UserHandler struct {
	users user.Repository
}

// NewUserHandler creates a UserHandler.
func NewUserHandler(users user.Repository) *UserHandler {
	return &UserHandler{users: users}
}

// Routes returns a chi router with user routes mounted.
func (h *UserHandler) Routes() chi.Router {
	r := chi.NewRouter()
	r.Get("/me", h.handleGetProfile)
	r.Patch("/me", h.handleUpdateProfile)
	return r
}

func (h *UserHandler) handleGetProfile(w http.ResponseWriter, r *http.Request) {
	uc, err := auth.UserFromContext(r.Context())
	if err != nil {
		server.Error(w, err)
		return
	}

	u, err := h.users.GetByID(r.Context(), uc.UserID)
	if err != nil {
		server.Error(w, err)
		return
	}

	server.JSON(w, http.StatusOK, map[string]any{
		"id":           u.ID,
		"email":        u.Email,
		"display_name": u.DisplayName,
		"created_at":   u.CreatedAt,
	})
}

func (h *UserHandler) handleUpdateProfile(w http.ResponseWriter, r *http.Request) {
	uc, err := auth.UserFromContext(r.Context())
	if err != nil {
		server.Error(w, err)
		return
	}

	var req struct {
		DisplayName string `json:"display_name"`
	}
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		server.JSON(w, http.StatusBadRequest, map[string]string{
			"code": "VALIDATION_ERROR", "message": "invalid request body",
		})
		return
	}

	u, err := h.users.GetByID(r.Context(), uc.UserID)
	if err != nil {
		server.Error(w, err)
		return
	}

	if err := u.UpdateDisplayName(req.DisplayName); err != nil {
		server.Error(w, err)
		return
	}

	if err := h.users.Update(r.Context(), u); err != nil {
		server.Error(w, err)
		return
	}

	server.JSON(w, http.StatusOK, map[string]any{
		"id":           u.ID,
		"email":        u.Email,
		"display_name": u.DisplayName,
	})
}
