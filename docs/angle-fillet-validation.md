# Angle Fillet Validation

FrameForge validates Equal Leg Angle and Unequal Leg Angle fillet parameters before geometry generation to prevent self-intersecting or invalid profiles and provide clear user diagnostics.

## Geometric Model

For angle profiles with fillets enabled (`MakeFillet = True`):

- **Root radius (`RadiusLarge`, $R$):** Fillets the inside corner between the two perpendicular legs.
- **Tip/corner radius (`RadiusSmall`, $r$):** Rounds the outer corner at the end (tip) of each leg. It is a corner rounding, not a full semicircular tip.
- **Leg thickness (`Thickness`, $T$):** The constant thickness of the angle legs.

## Validation Rules

When `MakeFillet = True`, validation runs after compatibility migrations and before profile geometry and weight/price updates. The following checks are enforced in the generator before geometry construction:

1. **Finite and strictly positive radii:**
   - Both `RadiusLarge` and `RadiusSmall` must be finite numbers (`not math.isnan(...)` and `not math.isinf(...)`).
   - Radii must be strictly positive:
     - `RadiusLarge cannot be negative, got <value>`
     - `RadiusLarge must be greater than zero for filleted angle profiles, got <value>`
     - `RadiusSmall cannot be negative, got <value>`
     - `RadiusSmall must be greater than zero for filleted angle profiles, got <value>`

2. **Tip radius cannot exceed leg thickness:**
   - $r \le T$
   - If $r > T$, the fillet would extend past the leg boundary and cause self-intersection.
   - Diagnostic: `RadiusSmall (<r>) cannot exceed Thickness (<T>) for filleted angle profiles`.
   - Equality ($r = T$) is fully supported.

3. **Fillets cannot overlap along any leg:**
   - The straight segment between the root fillet and the tip fillet along each leg requires:
     $$R + r \le W - T \quad \text{and} \quad R + r \le H - T$$
     which simplifies to:
     $$R + r \le \min(W, H) - T$$
   - If $R + r > \min(W, H) - T$, the root and tip fillets overlap along the shorter leg (or both legs if equal).
   - Diagnostic: `Fillet radii overlap: RadiusLarge (<R>) + RadiusSmall (<r>) = <R+r> exceeds available leg length min(ProfileWidth=<W>, ProfileHeight=<H>) - Thickness (<T>) = <available>`.
   - Equality ($R + r = \min(W, H) - T$), where adjacent fillets meet and the straight segment disappears, is supported.

## Behavior Invariants

- **Fillet-disabled profiles:** When `MakeFillet = False`, oversized or arbitrary radii values are ignored because no fillet arcs are constructed.
- **Other profile families:** Hollow tubes (`Square Hollow`, `Rectangular Hollow`) use `RadiusSmall` as the inner concentric radius, where $r > T$ is expected. Angular restrictions are strictly scoped to angle families (`Equal Leg Angles` and `Unequal Leg Angles`).
- **State preservation:** When validation fails:
  - Validation runs after compatibility migrations, and execution aborts before profile geometry generation and weight/price updates, leaving `obj.Shape`, `obj.ProfileLength`, `obj.ApproxWeight`, and `obj.Price` untouched.
  - The object's last valid shape (if previously computed) remains unchanged.
  - The user's entered parameter values are never silently clamped or modified.
  - FreeCAD marks the object invalid, displaying the exact diagnostic message in `obj.getStatusString()`.
  - Restoring valid parameters allows subsequent recomputation to succeed.
