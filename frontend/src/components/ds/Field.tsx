"use client";

import {
  createContext,
  forwardRef,
  useContext,
  useId,
  useRef,
  useState,
  type InputHTMLAttributes,
  type ReactNode,
  type SelectHTMLAttributes,
  type TextareaHTMLAttributes,
} from "react";
import { Spinner } from "./Button";
import { IconChevronDown, IconUpload } from "./icons";
import { cx } from "./tokens";

type FieldCtx = { id: string; describedBy?: string; invalid: boolean };
const Ctx = createContext<FieldCtx | null>(null);

/**
 * Form field wrapper: label, control, hint and error, wired for screen readers (id, aria-describedby,
 * aria-invalid flow into the Input/Textarea/Select inside via context).
 */
export function Field({
  label,
  hint,
  error,
  optional,
  children,
  className,
  id: idProp,
}: {
  label: ReactNode;
  hint?: ReactNode;
  error?: ReactNode;
  /** Shows "optional" after the label. Required is the default and is not marked. */
  optional?: boolean;
  children: ReactNode;
  className?: string;
  id?: string;
}) {
  const auto = useId();
  const id = idProp ?? auto;
  const hintId = hint ? `${id}-hint` : undefined;
  const errId = error ? `${id}-err` : undefined;
  const describedBy = [hintId, errId].filter(Boolean).join(" ") || undefined;
  return (
    <Ctx.Provider value={{ id, describedBy, invalid: !!error }}>
      <div className={cx("flex min-w-0 flex-col gap-1.5", className)}>
        <label htmlFor={id} className="text-small font-medium text-fg">
          {label}
          {optional && <span className="ml-1.5 font-normal text-fg-faint">optional</span>}
        </label>
        {children}
        {hint && !error && (
          <p id={hintId} className="text-micro text-fg-faint">
            {hint}
          </p>
        )}
        {error && (
          <p id={errId} role="alert" className="text-micro font-medium text-bad">
            {error}
          </p>
        )}
      </div>
    </Ctx.Provider>
  );
}

const CONTROL =
  "w-full min-w-0 rounded-field border bg-surface text-body text-fg placeholder:text-fg-faint " +
  "transition-[border-color,box-shadow] duration-200 outline-none " +
  "focus:border-accent focus:ring-4 focus:ring-accent-soft disabled:cursor-not-allowed disabled:bg-paper-2 disabled:text-fg-muted";

function useFieldProps(id?: string, invalid?: boolean) {
  const ctx = useContext(Ctx);
  const bad = invalid ?? ctx?.invalid ?? false;
  return {
    id: id ?? ctx?.id,
    "aria-describedby": ctx?.describedBy,
    "aria-invalid": bad || undefined,
    border: bad ? "border-bad" : "border-line-strong hover:border-line-bold",
  };
}

export type InputProps = Omit<InputHTMLAttributes<HTMLInputElement>, "prefix"> & {
  /** Text or icon inside the field on the left, e.g. a currency symbol "€". */
  prefix?: ReactNode;
  /** Text inside the field on the right, e.g. "units" or "%". */
  suffix?: ReactNode;
  invalid?: boolean;
};

/** Text input, 44px tall, 14px radius. Numbers: add `inputMode="decimal"` and a `prefix`/`suffix` for units. */
export const Input = forwardRef<HTMLInputElement, InputProps>(function Input(
  { prefix, suffix, invalid, className, id, ...rest },
  ref,
) {
  const { border, ...a11y } = useFieldProps(id, invalid);
  if (!prefix && !suffix) {
    return <input ref={ref} {...a11y} {...rest} className={cx(CONTROL, border, "h-11 px-3.5", className)} />;
  }
  return (
    <div className="relative flex items-center">
      {prefix && <span className="pointer-events-none absolute left-3.5 font-mono text-small text-fg-muted">{prefix}</span>}
      <input
        ref={ref}
        {...a11y}
        {...rest}
        className={cx(CONTROL, border, "h-11 tabular", prefix ? "pl-9" : "pl-3.5", suffix ? "pr-16" : "pr-3.5", className)}
      />
      {suffix && <span className="pointer-events-none absolute right-3.5 text-small text-fg-muted">{suffix}</span>}
    </div>
  );
});

/** Multi-line input. Grows with `rows`; resizes vertically only. */
export const Textarea = forwardRef<HTMLTextAreaElement, TextareaHTMLAttributes<HTMLTextAreaElement> & { invalid?: boolean }>(
  function Textarea({ invalid, className, id, rows = 4, ...rest }, ref) {
    const { border, ...a11y } = useFieldProps(id, invalid);
    return (
      <textarea
        ref={ref}
        rows={rows}
        {...a11y}
        {...rest}
        className={cx(CONTROL, border, "resize-y px-3.5 py-3 leading-relaxed", className)}
      />
    );
  },
);

/** Native select with the system chevron replaced. Use for 4+ options; fewer → <Segmented>. */
export const Select = forwardRef<HTMLSelectElement, SelectHTMLAttributes<HTMLSelectElement> & { invalid?: boolean }>(
  function Select({ invalid, className, id, children, ...rest }, ref) {
    const { border, ...a11y } = useFieldProps(id, invalid);
    return (
      <div className="relative">
        <select
          ref={ref}
          {...a11y}
          {...rest}
          className={cx(CONTROL, border, "h-11 cursor-pointer appearance-none pr-10 pl-3.5", className)}
        >
          {children}
        </select>
        <IconChevronDown size={16} className="pointer-events-none absolute top-1/2 right-3.5 -translate-y-1/2 text-fg-muted" />
      </div>
    );
  },
);

/**
 * Drop zone for files (mood boards, quote PDFs, CSVs): a stitched (dashed) panel that also opens the file
 * picker on click / Enter. Shows its own drag-over state; `busy` disables it with a spinner.
 * `layout="row"` puts the icon beside the text (a compact strip, e.g. above a table). `aria-label` names the
 * hidden file input (tests and the guided tour find it by that name); `zoneLabel` names the drop zone itself.
 */
export function FileDrop({
  onFiles,
  accept,
  multiple,
  title = "Drop files here",
  hint,
  busy,
  disabled,
  icon,
  layout = "stack",
  className,
  "data-demo": dataDemo,
  "aria-label": inputLabel,
  zoneLabel,
}: {
  onFiles: (files: File[]) => void;
  accept?: string;
  multiple?: boolean;
  title?: ReactNode;
  /** e.g. "PDF, PNG or JPG · up to 10 MB" */
  hint?: ReactNode;
  busy?: boolean;
  disabled?: boolean;
  icon?: ReactNode;
  layout?: "stack" | "row";
  className?: string;
  "data-demo"?: string;
  /** Accessible name of the file input. */
  "aria-label"?: string;
  /** Accessible name of the drop zone (defaults to its visible text). */
  zoneLabel?: string;
}) {
  const input = useRef<HTMLInputElement>(null);
  const [over, setOver] = useState(false);
  const off = disabled || busy;
  return (
    <div
      role="button"
      tabIndex={off ? -1 : 0}
      aria-disabled={off || undefined}
      aria-busy={busy || undefined}
      aria-label={zoneLabel}
      data-demo={dataDemo}
      onClick={() => !off && input.current?.click()}
      onKeyDown={(e) => {
        if (!off && (e.key === "Enter" || e.key === " ")) {
          e.preventDefault();
          input.current?.click();
        }
      }}
      onDragOver={(e) => {
        if (off) return;
        e.preventDefault();
        setOver(true);
      }}
      onDragLeave={() => setOver(false)}
      onDrop={(e) => {
        e.preventDefault();
        setOver(false);
        if (off) return;
        const files = Array.from(e.dataTransfer.files);
        if (files.length) onFiles(multiple ? files : files.slice(0, 1));
      }}
      className={cx(
        "group flex cursor-pointer rounded-panel border-[1.5px] border-dashed transition-colors duration-200",
        layout === "row"
          ? "items-center gap-4 px-5 py-5 text-left"
          : "flex-col items-center justify-center gap-3 px-6 py-8 text-center",
        over ? "border-accent bg-accent-soft" : "border-line-bold bg-surface hover:border-fg hover:bg-surface-muted",
        off && (busy ? "cursor-progress" : "cursor-not-allowed opacity-60"),
        className,
      )}
    >
      <span
        aria-hidden
        className={cx(
          "grid size-11 shrink-0 place-items-center rounded-full transition-colors",
          over ? "bg-accent text-on-accent" : "bg-paper-2 text-fg group-hover:bg-inverse group-hover:text-on-inverse",
        )}
      >
        {busy ? <Spinner /> : (icon ?? <IconUpload size={18} />)}
      </span>
      {layout === "row" ? (
        <span className="min-w-0">
          <span className="block text-body font-medium text-fg">{title}</span>
          {hint && <span className="mt-0.5 block text-micro text-fg-muted">{hint}</span>}
        </span>
      ) : (
        <>
          <span className="text-body font-medium text-fg">{title}</span>
          {hint && <span className="text-micro text-fg-muted">{hint}</span>}
        </>
      )}
      <input
        ref={input}
        type="file"
        hidden
        aria-label={inputLabel}
        accept={accept}
        multiple={multiple}
        onChange={(e) => {
          const files = Array.from(e.target.files ?? []);
          if (files.length) onFiles(files);
          e.target.value = "";
        }}
      />
    </div>
  );
}
