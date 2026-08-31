/**
 * The 5 phase accent colours (identify/protect/detect/respond/recover) and
 * dashboard gauge colours come from the backend as raw hex — e.g. Protect's
 * `#00ff88`, a neon green tuned to glow on a near-black background. Used
 * directly as text colour on the light theme's near-white background, that
 * same hex is badly under WCAG contrast (verified: ~1.8:1, need 4.5:1) — not
 * just "a bit washed out", genuinely unreadable. A single fixed
 * lightness-cap doesn't fix this uniformly: green contributes far more to
 * perceived luminance than blue or red (the WCAG formula weights it ~10x
 * blue), so the same HSL lightness reads as bright for green but already
 * dark for blue. readableAccent() instead darkens by actual computed
 * contrast ratio against the real light-theme background, per hue, until it
 * clears the threshold — not a guessed percentage.
 *
 * CSS custom property references (e.g. "var(--accent-blue)") are returned
 * unchanged — their light-mode values are already hand-tuned in theme.css.
 */

function hexToRgb(hex: string): [number, number, number] {
  const clean = hex.replace("#", "");
  const full = clean.length === 3 ? clean.split("").map((c) => c + c).join("") : clean;
  const int = parseInt(full, 16);
  return [(int >> 16) & 255, (int >> 8) & 255, int & 255];
}

function rgbToHsl(r: number, g: number, b: number): [number, number, number] {
  r /= 255; g /= 255; b /= 255;
  const max = Math.max(r, g, b);
  const min = Math.min(r, g, b);
  let h = 0;
  let s = 0;
  const l = (max + min) / 2;
  if (max !== min) {
    const d = max - min;
    s = l > 0.5 ? d / (2 - max - min) : d / (max + min);
    switch (max) {
      case r: h = (g - b) / d + (g < b ? 6 : 0); break;
      case g: h = (b - r) / d + 2; break;
      default: h = (r - g) / d + 4; break;
    }
    h /= 6;
  }
  return [h * 360, s * 100, l * 100];
}

function hslToRgb(h: number, s: number, l: number): [number, number, number] {
  s /= 100; l /= 100;
  const k = (n: number) => (n + h / 30) % 12;
  const a = s * Math.min(l, 1 - l);
  const f = (n: number) => l - a * Math.max(-1, Math.min(k(n) - 3, Math.min(9 - k(n), 1)));
  return [Math.round(f(0) * 255), Math.round(f(8) * 255), Math.round(f(4) * 255)];
}

function rgbToHex(r: number, g: number, b: number): string {
  const toHex = (x: number) => Math.max(0, Math.min(255, x)).toString(16).padStart(2, "0");
  return `#${toHex(r)}${toHex(g)}${toHex(b)}`;
}

// WCAG relative luminance — https://www.w3.org/TR/WCAG21/#dfn-relative-luminance
function relativeLuminance(r: number, g: number, b: number): number {
  const chan = (c: number) => {
    const v = c / 255;
    return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4);
  };
  return 0.2126 * chan(r) + 0.7152 * chan(g) + 0.0722 * chan(b);
}

function contrastRatio(l1: number, l2: number): number {
  const lighter = Math.max(l1, l2);
  const darker = Math.min(l1, l2);
  return (lighter + 0.05) / (darker + 0.05);
}

// Light theme's actual --bg-primary (#f1f4fa) — text sits on backgrounds at
// least this light throughout the app (cards are translucent over it), so
// contrast against this is the right target.
const LIGHT_BG_LUMINANCE = relativeLuminance(...hexToRgb("#f1f4fa"));
const TARGET_CONTRAST = 4.5; // WCAG AA, normal text

export function readableAccent(colour: string, theme: "dark" | "light"): string {
  if (theme === "dark" || !colour.startsWith("#")) return colour;
  const [r, g, b] = hexToRgb(colour);
  const [h, s] = rgbToHsl(r, g, b);
  const safeSaturation = Math.max(s, 55);

  // Step lightness down until the actual contrast ratio clears 4.5:1,
  // instead of guessing one fixed percentage that can't work for every hue.
  for (let l = 55; l >= 10; l -= 2) {
    const [cr, cg, cb] = hslToRgb(h, safeSaturation, l);
    const ratio = contrastRatio(relativeLuminance(cr, cg, cb), LIGHT_BG_LUMINANCE);
    if (ratio >= TARGET_CONTRAST) return rgbToHex(cr, cg, cb);
  }
  // Fell through (shouldn't happen for any real hue) — darkest safe fallback.
  const [cr, cg, cb] = hslToRgb(h, safeSaturation, 10);
  return rgbToHex(cr, cg, cb);
}
