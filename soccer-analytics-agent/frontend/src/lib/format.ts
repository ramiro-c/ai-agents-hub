/** Format a 0-1 probability as percentage string (e.g. 0.532 → "53%"). */
export function pct(n: number): string {
  return `${Math.round(n * 100)}%`;
}

/** Format a number with explicit sign (e.g. 42 → "+42", -7 → "-7"). */
export function signed(n: number): string {
  return n >= 0 ? `+${n}` : `${n}`;
}

/** Format a number to 2 decimal places (e.g. 2136.5 → "2136.50"). */
export function num2(n: number): string {
  return n.toFixed(2);
}
