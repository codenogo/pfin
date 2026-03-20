package adapters

import (
	"fmt"
	"time"

	"github.com/golang-jwt/jwt/v5"
	"github.com/google/uuid"
)

// Claims represents the custom JWT claims for pfin access tokens.
type Claims struct {
	UserID uuid.UUID `json:"sub"`
	Email  string    `json:"email"`
	jwt.RegisteredClaims
}

// TokenIssuer signs and validates JWT access tokens.
type TokenIssuer struct {
	secret    []byte
	accessTTL time.Duration
}

// NewTokenIssuer creates a new JWT token issuer.
func NewTokenIssuer(secret string, accessTTL time.Duration) *TokenIssuer {
	return &TokenIssuer{
		secret:    []byte(secret),
		accessTTL: accessTTL,
	}
}

// IssueAccessToken creates a signed JWT access token for the given user.
func (t *TokenIssuer) IssueAccessToken(userID uuid.UUID, email string) (string, error) {
	now := time.Now()
	claims := Claims{
		UserID: userID,
		Email:  email,
		RegisteredClaims: jwt.RegisteredClaims{
			IssuedAt:  jwt.NewNumericDate(now),
			ExpiresAt: jwt.NewNumericDate(now.Add(t.accessTTL)),
			Issuer:    "pfin",
		},
	}
	token := jwt.NewWithClaims(jwt.SigningMethodHS256, claims)
	signed, err := token.SignedString(t.secret)
	if err != nil {
		return "", fmt.Errorf("sign access token: %w", err)
	}
	return signed, nil
}

// ValidateAccessToken parses and validates a JWT string, returning claims.
func (t *TokenIssuer) ValidateAccessToken(tokenStr string) (*Claims, error) {
	token, err := jwt.ParseWithClaims(tokenStr, &Claims{}, func(token *jwt.Token) (any, error) {
		if _, ok := token.Method.(*jwt.SigningMethodHMAC); !ok {
			return nil, fmt.Errorf("unexpected signing method: %v", token.Header["alg"])
		}
		return t.secret, nil
	})
	if err != nil {
		return nil, fmt.Errorf("validate access token: %w", err)
	}
	claims, ok := token.Claims.(*Claims)
	if !ok || !token.Valid {
		return nil, fmt.Errorf("invalid token claims")
	}
	return claims, nil
}
