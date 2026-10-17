"use client";

// QA H5: when the backend has ATELIER_ADMIN_TOKEN set (the hosted demo), visitors can try every step up to Approve
// without it (backend security.PUBLIC_POSTS); approving emails real suppliers and opens a real Shopify pre-order, so
// that needs the token. This small form signs in (POST /api/auth/login sets an HttpOnly cookie). It never opens on
// load: only when a request comes back 401 "admin token required", or from Menu -> Sign in.

import { useEffect, useRef, useState, type FormEvent } from "react";
import { AUTH_CHANGED_EVENT, AUTH_REQUIRED_EVENT, errorMessage, getAuthStatus, signIn } from "@/lib/api";
import { Button, Eyebrow, Field, IconKey, Input, Modal } from "./ds";

/** The backend's sign-in state: `required` = a token is set; `signedIn` = this browser has it. Null until known. */
export function useAdminAuth(): { required: boolean; signedIn: boolean } | null {
  const [auth, setAuth] = useState<{ required: boolean; signedIn: boolean } | null>(null);
  useEffect(() => {
    let alive = true;
    const read = () =>
      getAuthStatus()
        .then((s) => alive && setAuth({ required: s.adminTokenRequired, signedIn: s.authenticated }))
        .catch(() => undefined); // backend down: the banner says so
    read();
    window.addEventListener(AUTH_CHANGED_EVENT, read);
    return () => {
      alive = false;
      window.removeEventListener(AUTH_CHANGED_EVENT, read);
    };
  }, []);
  return auth;
}

export function AdminLogin() {
  const [open, setOpen] = useState(false);
  const [token, setToken] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    const onRequired = () => setOpen(true);
    window.addEventListener(AUTH_REQUIRED_EVENT, onRequired);
    return () => window.removeEventListener(AUTH_REQUIRED_EVENT, onRequired);
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
      window.dispatchEvent(new Event(AUTH_CHANGED_EVENT));
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
      description="Approving a design emails real suppliers and opens a real Shopify pre-order, and the Brand workspace holds real supplier contacts, so those need the admin token. Every step before Approve is open to try without it."
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
