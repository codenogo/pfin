package errs

import (
	"fmt"
	"net/http"
)

// Error codes — machine-readable, stable identifiers.
const (
	CodeValidation      = "VALIDATION_ERROR"
	CodeNotFound        = "NOT_FOUND"
	CodeConflict        = "CONFLICT"
	CodeUnauthorized    = "UNAUTHORIZED"
	CodeForbidden       = "FORBIDDEN"
	CodeUnbalancedEntry = "UNBALANCED_ENTRY"
	CodeInternal        = "INTERNAL_ERROR"
)

// DomainError represents a domain-level error with a machine-readable code.
type DomainError struct {
	Code    string
	Message string
	Err     error
}

// Error implements the error interface.
func (e *DomainError) Error() string {
	if e.Err != nil {
		return fmt.Sprintf("%s: %s: %v", e.Code, e.Message, e.Err)
	}
	return fmt.Sprintf("%s: %s", e.Code, e.Message)
}

// Unwrap returns the wrapped error for errors.Is/As support.
func (e *DomainError) Unwrap() error {
	return e.Err
}

// New creates a DomainError with a code and message.
func New(code, message string) *DomainError {
	return &DomainError{Code: code, Message: message}
}

// Wrap creates a DomainError wrapping an existing error.
func Wrap(code, message string, err error) *DomainError {
	return &DomainError{Code: code, Message: message, Err: err}
}

// NotFound creates a NOT_FOUND error.
func NotFound(entity, id string) *DomainError {
	return New(CodeNotFound, fmt.Sprintf("%s %q not found", entity, id))
}

// Conflict creates a CONFLICT error.
func Conflict(message string) *DomainError {
	return New(CodeConflict, message)
}

// Validation creates a VALIDATION_ERROR.
func Validation(message string) *DomainError {
	return New(CodeValidation, message)
}

// Unauthorized creates an UNAUTHORIZED error.
func Unauthorized() *DomainError {
	return New(CodeUnauthorized, "authentication required")
}

// Forbidden creates a FORBIDDEN error.
func Forbidden(message string) *DomainError {
	return New(CodeForbidden, message)
}

// HTTPStatus maps the error code to an HTTP status code.
func (e *DomainError) HTTPStatus() int {
	switch e.Code {
	case CodeValidation, CodeUnbalancedEntry:
		return http.StatusBadRequest
	case CodeNotFound:
		return http.StatusNotFound
	case CodeConflict:
		return http.StatusConflict
	case CodeUnauthorized:
		return http.StatusUnauthorized
	case CodeForbidden:
		return http.StatusForbidden
	default:
		return http.StatusInternalServerError
	}
}
