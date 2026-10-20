# Agent text shimmer

## TSH-001: Follow the Agent lifecycle

- The running Agent status uses a text shimmer. A pending stop request, finished,
  stopped, paused, idle, confirmation, or error status restores static muted text.
- Toggling animation preserves the text element, content accessibility, title,
  truncation and layout. Existing completion confirmation timing stays intact.
- Sending and conversation-loading labels share the same restrained animation.

## TSH-002: Restrained text-only motion

- One soft highlight sweeps left to right every 2.8 seconds by default, looping
  with muted endpoints. The highlight brightens gray text without glow or shadows.
- Only glyph paint changes; backgrounds, font metrics and position do not animate.
- Reduced-motion and forced-colors preferences disable motion and restore static
  readable text, including on the initial render without JavaScript.
