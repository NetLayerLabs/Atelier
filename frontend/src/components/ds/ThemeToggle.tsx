"use client";

import { IconButton } from "./Button";
import { IconMoon, IconSun } from "./icons";
import { Segmented } from "./Tabs";
import { useTheme, type ThemePreference } from "./theme";

/** Round header control: switches light ↔ dark (projector) and remembers the choice. */
export function ThemeToggle({ className, size = "md" }: { className?: string; size?: "sm" | "md" | "lg" }) {
  const { theme, toggle, ready } = useTheme();
  const dark = ready && theme === "dark";
  return (
    <IconButton
      label={dark ? "Switch to light theme" : "Switch to dark theme (projector)"}
      variant="soft"
      size={size}
      onClick={toggle}
      className={className}
    >
      {dark ? <IconSun size={16} /> : <IconMoon size={16} />}
    </IconButton>
  );
}

/** Light / Dark / System segmented control (for the menu and settings). */
export function ThemeSegmented({ className }: { className?: string }) {
  const { preference, setPreference, ready } = useTheme();
  return (
    <Segmented<ThemePreference>
      label="Theme"
      size="sm"
      className={className}
      value={ready ? preference : "system"}
      onChange={setPreference}
      options={[
        { value: "light", label: "Light" },
        { value: "dark", label: "Dark" },
        { value: "system", label: "System" },
      ]}
    />
  );
}
