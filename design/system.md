# FreeCAD TaskPanel Design System

Tokens and styling conventions for FreeCAD MaxProFrame task panels and dialogs, based on FreeCAD Qt Dark stylesheet and native widgets.

## Colors

| Token | Value | Usage |
| --- | --- | --- |
| `--fc-bg-window` | `#2b2b2b` | Task panel & dialog window background |
| `--fc-bg-surface` | `#333333` | Group boxes, cards, widget containers |
| `--fc-bg-input` | `#222222` | Text boxes, spinboxes, combo boxes |
| `--fc-bg-input-hover` | `#282828` | Hover state for input controls |
| `--fc-bg-selection` | `#2a6fc9` | Selected list item, active tab, anchor dot |
| `--fc-bg-selection-hover` | `#3882e3` | Hover on selectable items |
| `--fc-bg-canvas` | `#1c1c1c` | 2D section drawing viewport / preview area |
| `--fc-border-subtle` | `#3e3e3e` | Internal dividers, subtle borders |
| `--fc-border-medium` | `#4a4a4a` | Group box borders, input borders |
| `--fc-border-focus` | `#2a6fc9` | Focused input border |
| `--fc-text-primary` | `#e0e0e0` | Main text, labels, button text |
| `--fc-text-secondary` | `#9e9e9e` | Unit suffixes, helper guidance, captions |
| `--fc-text-dim` | `#6e6e6e` | Disabled labels, placeholder text |
| `--fc-text-link` | `#4fa3ff` | Interactive links and tags |
| `--fc-badge-bg` | `#3a3a3a` | Compact status tags and pill badges |
| `--fc-badge-text` | `#d0d0d0` | Text on badges |
| `--fc-btn-bg` | `#3a3a3a` | Default push button background |
| `--fc-btn-hover` | `#454545` | Push button hover |
| `--fc-btn-active` | `#252525` | Push button pressed |
| `--fc-danger` | `#c93b3b` | Delete, remove edge, warning |

## Typography

- **Font family**: `system-ui, -apple-system, "Segoe UI", Roboto, "Cantarell", "Ubuntu", sans-serif`
- **Monospace font**: `ui-monospace, "SF Mono", "Consolas", "Liberation Mono", monospace`
- **Scale**:
  - Base: `12px` (standard FreeCAD UI font size)
  - Small / Caption: `11px`
  - Group Box Title: `12px`, font-weight `600`
  - Header / Dialog Title: `13px`, font-weight `600`

## Spacing & Metrics

- Standard TaskPanel width: `360px` (min `320px`, max `420px`)
- Standard control height: `26px`
- Input padding: `3px 7px`
- GroupBox margin-top: `12px`
- Form row spacing: `6px`
- Radius: `3px` (subtle Qt style)
