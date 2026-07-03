package main

import "testing"

func TestAdd(t *testing.T) {
	if got := Add(2, 3); got != 5 {
		t.Errorf("Add(2,3) = %d; want 5", got)
	}
	if got := Add(-2, 3); got != 1 {
		t.Errorf("Add(-2,3) = %d; want 1", got)
	}
}

func TestSubtract(t *testing.T) {
	if got := Subtract(5, 3); got != 2 {
		t.Errorf("Subtract(5,3) = %d; want 2", got)
	}
}

func TestMultiply(t *testing.T) {
	if got := Multiply(2, 3); got != 6 {
		t.Errorf("Multiply(2,3) = %d; want 6", got)
	}
	if got := Multiply(5, 0); got != 0 {
		t.Errorf("Multiply(5,0) = %d; want 0", got)
	}
}

func TestDivide(t *testing.T) {
	got, err := Divide(6, 3)
	if err != nil {
		t.Fatalf("Divide(6,3) returned unexpected error: %v", err)
	}
	if got != 2 {
		t.Errorf("Divide(6,3) = %f; want 2", got)
	}

	if _, err := Divide(5, 0); err == nil {
		t.Error("Divide(5,0) should return error")
	}
}
