-- Sample Lean 4 file exercising every kind the extractor exposes.
-- Hand-written for tests — no fixtures pulled verbatim from any other project.

namespace SampleNs

inductive Color where
  | red
  | green
  | blue

structure Point where
  x : Nat
  y : Nat

class HasZero (α : Type) where
  zero : α

def greet (name : String) : String := name

@[simp]
theorem add_zero (n : Nat) : n + 0 = n := by simp

example : 1 + 1 = 2 := rfl

abbrev Age := Nat

instance natHasZero : HasZero Nat where
  zero := 0

axiom truth : True
opaque secret : Nat := 42

def Point.origin : Point := { x := 0, y := 0 }

-- @@start example-block
def withMarker (n : Nat) : Nat := n * 2
-- @@end example-block

end SampleNs

section

def topLevel : Nat := 0

end

namespace Outer
namespace Inner

def deeplyNested : String := "hi"

end Inner
end Outer

namespace MutualNs

mutual

def evenN : Nat → Bool
  | 0 => true
  | n + 1 => oddN n

def oddN : Nat → Bool
  | 0 => false
  | n + 1 => evenN n

end

def afterMutual : Nat := 42

end MutualNs
