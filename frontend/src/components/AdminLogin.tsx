"use client";

// QA H5: when the backend has ATELIER_ADMIN_TOKEN set, every change needs the token. This small form signs in
// (POST /api/auth/login sets an HttpOnly cookie) and opens on load when the backend says a token is required, or
// whenever a request comes back 401 "admin token required". Without a token configured it never shows: the backend
// then accepts changes from this machine only.

import { useEffect, useRef, useState, type FormEvent } from "react";
import { AUTH_REQUIRED_EVENT, errorMessage, getAuthStatus, signIn } from "@/lib/api";
import { Button, Eyebrow, Field, IconKey, Input, Modal } from "./ds";

export function AdminLogin() {
  const [open, setOpen] = useState(false);
  const [token, setToken] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    let alive = true;
    getAuthStatus()
      .then((s) => {
        if (alive && s.adminTokenRequired && !s.authenticated) setOpen(true);
      })
      .catch(() => undefined); // backend down: the banner says so
    const onRequired = () => setOpen(true);
    window.addEventListener(AUTH_REQUIRED_EVENT, onRequired);
    return () => {
      alive = false;
      window.removeEventListener(AUTH_REQUIRED_EVENT, onRequired);
    };
  }, []);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    if (!token.trim()) return;
    setBusy(true);
    setError(null);
    try {
      await signIn(token.trim());
      setToken("");
      setOpen(false);
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Modal
      open={open}
      onClose={() => setOpen(false)}
      eyebrow={<Eyebrow tone="accent">Admin token</Eyebrow>}
      title="Sign in"
      description="This Atelier backend requires its admin token (ATELIER_ADMIN_TOKEN) for changes and private files."
      initialFocus={inputRef}
    >
      <form onSubmit={submit} className="flex flex-col gap-6">
        <Field label="Admin token" error={error ?? undefined}>
          <Input
            ref={inputRef}
            type="password"
            autoComplete="current-password"
            value={token}
            onChange={(e) => setToken(e.target.value)}
          />
        </Field>
        <div className="flex items-center justify-end gap-2">
          <Button type="button" variant="ghost" onClick={() => setOpen(false)}>
            Not now
          </Button>
          <Button type="submit" loading={busy} disabled={!token.trim()} icon={<IconKey size={16} />}>
            {busy ? "Signing in…" : "Sign in"}
          </Button>
        </div>
      </form>
    </Modal>
  );
}
