import { useSyncExternalStore } from "react";

const KEY = "munim.hide-numbers";
const listeners = new Set<() => void>();

const read = () => {
  try {
    return window.localStorage.getItem(KEY) === "1";
  } catch {
    return false; // storage can be blocked; fall back to showing numbers
  }
};

let hidden = read();

export const isHidden = () => hidden;

export function setHidden(next: boolean) {
  hidden = next;
  try {
    window.localStorage.setItem(KEY, next ? "1" : "0");
  } catch {
    /* keep the in-memory value */
  }
  listeners.forEach((l) => l());
}

/** Re-renders the caller when the eye is toggled. */
export const useHidden = () =>
  useSyncExternalStore(
    (cb) => {
      listeners.add(cb);
      return () => listeners.delete(cb);
    },
    () => hidden,
  );

export const STARS = "****";

// Amounts (₹ or Rs, with optional k/L/Cr/lakh/crore), percentages, and any other number
// that isn't a year. Years and the digits inside words are left alone.
const NUMBER = /(?:₹|Rs\.?\s?)?-?\b(?!(?:19|20)\d{2}\b)\d[\d,]*(?:\.\d+)?\s?(?:%|k\b|L\b|Cr\b|lakhs?\b|crores?\b)?/gi;

/** Free text (written answers, fact lines): numbers become asterisks while hidden. */
export const maskText = (text: string) => (hidden ? text.replace(NUMBER, STARS) : text);
