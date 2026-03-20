package session

import (
	"testing"
	"time"

	"github.com/google/uuid"
)

func TestGenerateToken(t *testing.T) {
	raw, hash, err := GenerateToken()
	if err != nil {
		t.Fatalf("GenerateToken: %v", err)
	}
	if len(raw) != 64 { // 32 bytes hex encoded
		t.Errorf("raw token length = %d, want 64", len(raw))
	}
	if raw == hash {
		t.Error("raw and hash should differ")
	}
	if HashToken(raw) != hash {
		t.Error("HashToken(raw) should equal returned hash")
	}
}

func TestGenerateToken_Uniqueness(t *testing.T) {
	raw1, _, _ := GenerateToken()
	raw2, _, _ := GenerateToken()
	if raw1 == raw2 {
		t.Error("two generated tokens should be different")
	}
}

func TestNewRefreshToken(t *testing.T) {
	uid := uuid.New()
	rt := NewRefreshToken(uid, "somehash", 14*24*time.Hour)
	if rt.UserID != uid {
		t.Errorf("UserID = %v, want %v", rt.UserID, uid)
	}
	if rt.Revoked {
		t.Error("new token should not be revoked")
	}
	if rt.IsExpired() {
		t.Error("new token should not be expired")
	}
	if !rt.IsValid() {
		t.Error("new token should be valid")
	}
}

func TestIsExpired(t *testing.T) {
	uid := uuid.New()
	rt := NewRefreshToken(uid, "hash", -1*time.Hour) // already expired
	if !rt.IsExpired() {
		t.Error("token with past expiry should be expired")
	}
	if rt.IsValid() {
		t.Error("expired token should not be valid")
	}
}

func TestIsValid_Revoked(t *testing.T) {
	uid := uuid.New()
	rt := NewRefreshToken(uid, "hash", 24*time.Hour)
	rt.Revoked = true
	if rt.IsValid() {
		t.Error("revoked token should not be valid")
	}
}
