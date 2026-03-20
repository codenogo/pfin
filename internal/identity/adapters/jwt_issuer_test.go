package adapters

import (
	"testing"
	"time"

	"github.com/google/uuid"
)

func TestIssueAndValidate(t *testing.T) {
	issuer := NewTokenIssuer("test-secret-key-32chars-long!!", 15*time.Minute)
	userID := uuid.New()
	email := "test@example.com"

	token, err := issuer.IssueAccessToken(userID, email)
	if err != nil {
		t.Fatalf("IssueAccessToken: %v", err)
	}
	if token == "" {
		t.Fatal("token should not be empty")
	}

	claims, err := issuer.ValidateAccessToken(token)
	if err != nil {
		t.Fatalf("ValidateAccessToken: %v", err)
	}
	if claims.UserID != userID {
		t.Errorf("UserID = %v, want %v", claims.UserID, userID)
	}
	if claims.Email != email {
		t.Errorf("Email = %q, want %q", claims.Email, email)
	}
}

func TestValidate_ExpiredToken(t *testing.T) {
	issuer := NewTokenIssuer("test-secret", -1*time.Minute) // already expired
	token, _ := issuer.IssueAccessToken(uuid.New(), "a@b.com")

	_, err := issuer.ValidateAccessToken(token)
	if err == nil {
		t.Error("should reject expired token")
	}
}

func TestValidate_TamperedToken(t *testing.T) {
	issuer := NewTokenIssuer("secret-a", 15*time.Minute)
	token, _ := issuer.IssueAccessToken(uuid.New(), "a@b.com")

	other := NewTokenIssuer("secret-b", 15*time.Minute)
	_, err := other.ValidateAccessToken(token)
	if err == nil {
		t.Error("should reject token signed with different secret")
	}
}

func TestValidate_GarbageToken(t *testing.T) {
	issuer := NewTokenIssuer("secret", 15*time.Minute)
	_, err := issuer.ValidateAccessToken("not.a.jwt")
	if err == nil {
		t.Error("should reject garbage token")
	}
}
