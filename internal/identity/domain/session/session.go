package session

import (
	"crypto/rand"
	"crypto/sha256"
	"encoding/hex"
	"fmt"
	"time"

	"github.com/google/uuid"
)

// RefreshToken represents a session refresh token stored server-side.
type RefreshToken struct {
	ID        uuid.UUID
	UserID    uuid.UUID
	TokenHash string
	ExpiresAt time.Time
	Revoked   bool
	CreatedAt time.Time
}

// GenerateToken creates a cryptographically random token and its SHA-256 hash.
// Returns (rawToken, hashedToken, error). The raw token is sent to the client;
// only the hash is stored in the database.
func GenerateToken() (string, string, error) {
	b := make([]byte, 32)
	if _, err := rand.Read(b); err != nil {
		return "", "", fmt.Errorf("generate token: %w", err)
	}
	raw := hex.EncodeToString(b)
	return raw, HashToken(raw), nil
}

// HashToken computes the SHA-256 hash of a raw token string.
func HashToken(raw string) string {
	h := sha256.Sum256([]byte(raw))
	return hex.EncodeToString(h[:])
}

// NewRefreshToken creates a RefreshToken entity from a raw token.
func NewRefreshToken(userID uuid.UUID, tokenHash string, ttl time.Duration) *RefreshToken {
	return &RefreshToken{
		ID:        uuid.New(),
		UserID:    userID,
		TokenHash: tokenHash,
		ExpiresAt: time.Now().Add(ttl),
		Revoked:   false,
		CreatedAt: time.Now(),
	}
}

// IsExpired returns true if the token has passed its expiry time.
func (t *RefreshToken) IsExpired() bool {
	return time.Now().After(t.ExpiresAt)
}

// IsValid returns true if the token is neither expired nor revoked.
func (t *RefreshToken) IsValid() bool {
	return !t.Revoked && !t.IsExpired()
}
