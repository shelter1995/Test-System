# Workspace Page Frame Unification Design

## Goal

Remove the visible width jump when switching between knowledge chat, content generation, and tutor pages while preserving each page's appropriate internal composition.

## Current Measurements

At a 1249px viewport with a 220px sidebar:

- Knowledge chat page frame: about 973px.
- Content generation page frame: about 973px; primary card: about 940px.
- Tutor welcome card: 780px.

The tutor welcome card is roughly 160px narrower than the content generation card and is the main source of the transition discontinuity.

## Shared Frame Contract

Knowledge chat, content generation, and tutor use a shared outer frame:

```css
width: 100%;
max-width: 1200px;
margin-inline: auto;
min-width: 0;
```

The frame fills the available content area below 1200px and remains centered on wider screens. Existing responsive breakpoints continue to control each page's internal columns.

## Page Composition

### Knowledge Chat

Keep the existing two-card question/source grid. Apply the shared frame to `.kbchat-page`; do not wrap the two cards in another decorative card.

### Content Generation

Apply the shared frame to the generation page root. Keep its single working card and current internal section structure. Normalize only the outer frame and horizontal centering.

### Tutor

Apply the shared frame to tutor start, chat, and report content:

- Expand `.welcome-card` from its current 780px cap to the shared available width.
- Constrain the chat layout and report content to the shared frame while preserving their full-height flex and internal scrolling.
- Keep fixed history drawers, backdrops, and modal dialogs outside the shared frame.

Tutor pages retain their current background bands and vertical behavior. The change does not flatten all pages into one identical card.

## Responsive Behavior

- Desktop: all three page frames share the 1200px maximum and centered alignment.
- Medium widths: frames fill the available content width with the existing page padding.
- Mobile: frames remain `width: 100%`; existing single-column layouts and bottom navigation continue to apply.
- No page may increase `document.body.scrollWidth` beyond the viewport.

## Testing

- Add a static CSS regression test for the shared frame selectors and 1200px contract.
- Verify knowledge chat, content generation, tutor start, tutor chat, and tutor report widths through browser-computed bounding boxes.
- Verify fixed drawers and modals remain viewport anchored rather than frame constrained.
- Check desktop and 390px mobile screenshots for clipping, overflow, and abrupt horizontal shifts.
- Run the full Python and Node test suites.
