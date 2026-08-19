---
name: Operational Intelligence
colors:
  surface: '#0b1326'
  surface-dim: '#0b1326'
  surface-bright: '#31394d'
  surface-container-lowest: '#060e20'
  surface-container-low: '#131b2e'
  surface-container: '#171f33'
  surface-container-high: '#222a3d'
  surface-container-highest: '#2d3449'
  on-surface: '#dae2fd'
  on-surface-variant: '#c7c4d7'
  inverse-surface: '#dae2fd'
  inverse-on-surface: '#283044'
  outline: '#908fa0'
  outline-variant: '#464554'
  surface-tint: '#c0c1ff'
  primary: '#c0c1ff'
  on-primary: '#1000a9'
  primary-container: '#8083ff'
  on-primary-container: '#0d0096'
  inverse-primary: '#494bd6'
  secondary: '#adc6ff'
  on-secondary: '#002e6a'
  secondary-container: '#0566d9'
  on-secondary-container: '#e6ecff'
  tertiary: '#ffb783'
  on-tertiary: '#4f2500'
  tertiary-container: '#d97721'
  on-tertiary-container: '#452000'
  error: '#ffb4ab'
  on-error: '#690005'
  error-container: '#93000a'
  on-error-container: '#ffdad6'
  primary-fixed: '#e1e0ff'
  primary-fixed-dim: '#c0c1ff'
  on-primary-fixed: '#07006c'
  on-primary-fixed-variant: '#2f2ebe'
  secondary-fixed: '#d8e2ff'
  secondary-fixed-dim: '#adc6ff'
  on-secondary-fixed: '#001a42'
  on-secondary-fixed-variant: '#004395'
  tertiary-fixed: '#ffdcc5'
  tertiary-fixed-dim: '#ffb783'
  on-tertiary-fixed: '#301400'
  on-tertiary-fixed-variant: '#703700'
  background: '#0b1326'
  on-background: '#dae2fd'
  surface-variant: '#2d3449'
typography:
  display-lg:
    fontFamily: Inter
    fontSize: 30px
    fontWeight: '600'
    lineHeight: 38px
    letterSpacing: -0.02em
  headline-md:
    fontFamily: Inter
    fontSize: 20px
    fontWeight: '600'
    lineHeight: 28px
  title-sm:
    fontFamily: Inter
    fontSize: 16px
    fontWeight: '500'
    lineHeight: 24px
  body-md:
    fontFamily: Inter
    fontSize: 14px
    fontWeight: '400'
    lineHeight: 20px
  body-sm:
    fontFamily: Inter
    fontSize: 13px
    fontWeight: '400'
    lineHeight: 18px
  code-table:
    fontFamily: JetBrains Mono
    fontSize: 12px
    fontWeight: '400'
    lineHeight: 16px
  label-caps:
    fontFamily: Inter
    fontSize: 11px
    fontWeight: '700'
    lineHeight: 16px
    letterSpacing: 0.05em
rounded:
  sm: 0.125rem
  DEFAULT: 0.25rem
  md: 0.375rem
  lg: 0.5rem
  xl: 0.75rem
  full: 9999px
spacing:
  unit: 4px
  container-padding: 24px
  element-gap: 12px
  table-row-height: 40px
  sidebar-width: 260px
---

## Brand & Style

This design system is engineered for high-stakes enterprise environments where clarity, speed of cognition, and system reliability are paramount. The aesthetic follows a **Corporate / Modern** approach with a heavy emphasis on **Functional Minimalism**. 

The interface is designed to function as a professional cockpit. It prioritizes information density without sacrificing legibility, utilizing a strict grid and clear visual hierarchy to manage complex data streams. Every element serves a functional purpose, eschewing decorative flourishes like gradients or rounded "chatbot" metaphors in favor of a technical, "instrument cluster" feel. The emotional response should be one of control, precision, and institutional trust.

## Colors

The palette is optimized for long-duration monitoring. The default mode is **Dark**, utilizing a deep slate foundation to reduce eye strain and allow status indicators to remain highly visible.

- **Backgrounds:** Use Slate-950 (`#020617`) for the primary canvas and Slate-900 (`#0F172A`) for elevated panels or containers.
- **Primary Accent:** Indigo-500 (`#6366F1`) is reserved for primary actions and system-level focus states.
- **Operational Status:**
    - **Emerald (Success/Deterministic):** Indicates completed tasks or hard-coded logic paths.
    - **Amber (AI Discovery/Human Required):** Indicates non-deterministic AI reasoning or a state requiring manual intervention.
    - **Rose (Failure/Intervention):** High-priority alerts requiring immediate attention.
    - **Blue (Running/Automation):** Active processes currently under machine control.

## Typography

Typography is treated as a data-delivery mechanism. **Inter** provides high legibility for UI controls and labels, while **JetBrains Mono** is utilized for technical identifiers, log entries, and tabular data to ensure character alignment and readability.

For mobile views, `display-lg` should scale down to 24px/32px. Use `label-caps` for table headers and section dividers to create clear boundaries between data sets. Tabular numbers should always use monospaced features to prevent "shimmering" during real-time data updates.

## Layout & Spacing

The system uses a **Fixed Grid** for internal dashboards. A 12-column grid is standard for desktop, with a permanent left-hand navigation sidebar (260px). 

The spacing rhythm is based on a **4px base unit**. For high-density enterprise views, use tight padding (12px) within cards and tables. 

**Breakpoints:**
- **Desktop (1280px+):** 12-column, fixed margins.
- **Tablet (768px - 1279px):** 8-column, fluid margins.
- **Mobile (<767px):** 4-column, full-bleed cards with 16px horizontal margins. 
- Sidebars collapse to icon-only rails on Tablet and hidden drawers on Mobile.

## Elevation & Depth

This design system uses **Tonal Layers** rather than traditional shadows to maintain a flat, professional "instrumentation" aesthetic.

- **Level 0 (Canvas):** Slate-950. The base background for the entire application.
- **Level 1 (Panels):** Slate-900. Used for cards, sidebars, and main content containers.
- **Level 2 (Modals/Popovers):** Slate-800. These use a 1px border of Slate-700 to provide definition against lower levels.

**Outlines:** Use a "Ghost Border" technique. Every interactive element (inputs, buttons, cards) should have a subtle 1px border (`rgba(255,255,255,0.1)`) instead of drop shadows to define its footprint in the dark UI.

## Shapes

The shape language is **Soft (0.25rem)**. This slight rounding provides a modern touch without appearing consumer-oriented or "bubbly."

- **Small elements:** (Checkboxes, Tags, Input fields) use 4px radius.
- **Medium elements:** (Cards, Modals) use 8px radius.
- **Large elements:** (Main container areas) use 12px radius.

Buttons and Status Badges should never be fully pill-shaped; keep them rectangular with the standard 4px radius to reinforce the industrial/enterprise feel.

## Components

### Status Badges
- **DETERMINISTIC:** Solid background (Emerald-900), Emerald-400 text, 1px Emerald-700 border. No icon.
- **AI DISCOVERY:** Subtle Amber-500/10% background, Amber-500 text, 1px Amber-500/30% border. Feature a "Sparkle" or "AI" icon.

### Data Tables
Tables are the primary view. Rows are 40px high. Header cells use `label-caps` typography. Hover states should highlight the entire row with a Slate-800 background. Use monospaced font for all numerical values.

### Execution Timelines
Vertical lines (2px, Slate-800) connecting nodes. 
- **Machine Node:** Blue circle (8px).
- **Human Node:** Indigo square (8px).
- **Branching Node:** Amber diamond (8px).

### Control Ownership Indicators
A persistent toggle or badge in the header of cards:
- **AUTOMATION:** Blue pulse indicator with "SYSTEM-CONTROL" label.
- **MANUAL:** Indigo solid indicator with "OPERATOR-REQUIRED" label.

### Buttons & Inputs
Buttons use `body-sm` bold text. Primary buttons are Indigo-500 with white text. Secondary buttons are transparent with a Slate-700 border. Inputs use Slate-950 backgrounds with a 1px Slate-700 border that brightens to Indigo-500 on focus.