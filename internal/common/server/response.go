package server

import (
	"encoding/json"
	"errors"
	"net/http"

	"github.com/codenogo/pfin/pkg/errs"
)

// JSON writes a JSON response with the given status code.
func JSON(w http.ResponseWriter, status int, data any) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	json.NewEncoder(w).Encode(data)
}

// Error writes a JSON error response, mapping DomainError to appropriate HTTP status.
func Error(w http.ResponseWriter, err error) {
	var domErr *errs.DomainError
	if errors.As(err, &domErr) {
		JSON(w, domErr.HTTPStatus(), map[string]string{
			"code":    domErr.Code,
			"message": domErr.Message,
		})
		return
	}
	JSON(w, http.StatusInternalServerError, map[string]string{
		"code":    errs.CodeInternal,
		"message": "internal server error",
	})
}
