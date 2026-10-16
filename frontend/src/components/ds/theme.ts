"use client";

import { useEffect, useState } from "react";
import { THEME_STORAGE_KEY } from "./theme-script";

export { THEME_STORAGE_KEY };

/**
 * Theme handling. Light is the default; dark is the "projector" theme.
 *
 * The inline script in app/layout.tsx (THEME_SCRIPT) resolves the theme before the first paint and writes
 * `<html data-theme="light|dark">`: `?theme=dark|light` in the URL wins (and is stored), then a stored choice,
 * then the OS preference. With no stored choice the page follows OS changes live.
 */
export type Theme = "light" | "dark";
export type ThemePreference = Theme | "system";

function systemTheme(): Theme {
  return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

function readPreference(): ThemePreference {
  try {
    const s = localStorage.getItem(THEME_STORAGE_KEY);
    return s === "light" || s === "dark" ? s : "system";
  } catch {
    return "system";
  }
}

function apply(theme: Theme) {
  const d = document.documentElement;
  d.setAttribute("data-theme", theme);
  d.style.colorScheme = theme;
  window.dispatchEvent(new CustomEvent<Theme>("atelier-theme", { detail: theme }));
}

/** Set the theme preference ("system" clears the stored choice and follows the OS). */
export function setThemePreference(pref: ThemePreference) {
  try {
    if (pref === "system") localStorage.removeItem(THEME_STORAGE_KEY);
    else localStorage.setItem(THEME_STORAGE_KEY, pref);
  } catch {
    /* storage unavailable: still apply for this page view */
  }
  apply(pref === "system" ? systemTheme() : pref);
}

/**
 * The resolved theme and the stored preference, kept in sync with the toggle, other tabs and the OS.
 * Before hydration it reports "light" (the server default); `ready` turns true after mount.
 */
export function useTheme() {
  const [state, setState] = useState<{ theme: Theme; preference: ThemePreference; ready: boolean }>({
    theme: "light",
    preference: "system",
    ready: false,
  });

  useEffect(() => {
    const sync = () => {
      const attr = document.documentElement.getAttribute("data-theme");
      setState({
        theme: attr === "dark" ? "dark" : "light",
        preference: readPreference(),
        ready: true,
      });
    };
    sync();
    const mq = window.matchMedia("(prefers-color-scheme: dark)");
    const onSystem = () => {
      if (readPreference() === "system") apply(systemTheme());
    };
    const onStorage = (e: StorageEvent) => {
      if (e.key !== THEME_STORAGE_KEY) return;
      const p = readPreference();
      apply(p === "system" ? systemTheme() : p);
    };
    mq.addEventListener("change", onSystem);
    window.addEventListener("storage", onStorage);
    window.addEventListener("atelier-theme", sync);
    return () => {
      mq.removeEventListener("change", onSystem);
      window.removeEventListener("storage", onStorage);
      window.removeEventListener("atelier-theme", sync);
    };
  }, []);

  return {
    ...state,
    setPreference: setThemePreference,
    toggle: () => setThemePreference(state.theme === "dark" ? "light" : "dark"),
  };
}
