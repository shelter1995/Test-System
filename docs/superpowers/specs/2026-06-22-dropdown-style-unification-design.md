# Dropdown Style Unification Design

## Goal

Unify all form dropdown controls in the local workbench so native selects and custom database pickers have the same visual weight and interaction feedback.

## Scope

The change covers:

- Tutor scenario and scenario-type selects.
- Tutor database custom picker.
- Knowledge chat database custom picker.
- Generation form selects.
- History filter select.
- Model settings provider, model, and test-target selects.

Popup panels such as the top-bar artifact history menu are not form dropdown controls and remain unchanged.

## Visual Contract

Every covered control uses:

- A 42px stable height.
- A 1px solid `#cfd8e3` border.
- The existing medium control radius.
- Consistent horizontal padding and inherited typography.
- A compact CSS chevron rather than a text glyph.
- A blue focus border with a restrained three-pixel focus ring.
- Matching disabled opacity and cursor behavior.

Custom dropdown menus retain their existing width, scrolling, selected state, z-index, and keyboard behavior. Native selects keep native selection behavior while using a shared visual class contract.

## Implementation

Add shared dropdown design tokens and grouped CSS rules in `style.css`. Existing component selectors remain available for component-specific layout, while duplicated border, height, radius, typography, and focus declarations are replaced or overridden by the shared contract.

No JavaScript data flow or selection behavior changes are required.

Update the stylesheet cache version in `index.html` so an ordinary browser refresh loads the unified styling.

## Verification

- Add a static regression test that enumerates the covered selectors and checks the shared 42px/1px contract.
- Run existing tutor database and knowledge chat dropdown tests.
- Verify representative dropdowns in knowledge chat, tutor setup, generation, history, and model settings.
- Check desktop and 390px mobile layouts for clipping, overflow, menu alignment, and focus state.
- Confirm no relevant browser console warnings or errors.
