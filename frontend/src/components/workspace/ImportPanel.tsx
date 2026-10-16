"use client";

import { useState, type ReactNode } from "react";
import {
  Badge,
  Button,
  buttonClass,
  cx,
  FileDrop,
  IconArrowDown,
  IconCheck,
  InlineAlert,
  Label,
  Segmented,
  Sparkline,
  Table,
  TBody,
  Td,
  Th,
  THead,
  Tr,
} from "@/components/ds";
import { errorMessage } from "@/lib/api";
import { importTable, templateUrl, type ImportKind, type ImportPreview } from "@/lib/workspace";

/** Drag-and-drop (or click) file picker: the design-system FileDrop with a single-file callback. */
export function DropZone({
  accept,
  hint,
  onFile,
  busy,
  label = "Drop a file here, or click to choose",
}: {
  accept: string;
  hint: ReactNode;
  onFile: (f: File) => void;
  busy?: boolean;
  label?: string;
}) {
  return (
    <FileDrop
      accept={accept}
      busy={busy}
      title={busy ? "Reading…" : label}
      hint={hint}
      onFiles={(files) => files[0] && onFile(files[0])}
    />
  );
}

/** Columns shown in the preview table per import kind (camelCase keys of the preview rows). */
const PREVIEW_COLUMNS: Record<ImportKind, [string, string][]> = {
  suppliers: [
    ["name", "Name"],
    ["city", "City"],
    ["country", "Country"],
    ["language", "Lang"],
    ["contactEmails", "Contacts"],
    ["categories", "Categories"],
    ["certifications", "Certifications"],
    ["moq", "MOQ"],
    ["leadTimeWeeks", "Lead (wks)"],
    ["paymentTerms", "Terms"],
    ["rfqEmailOverride", "RFQ override"],
  ],
  prices: [
    ["material", "Material"],
    ["category", "Category"],
    ["unit", "Unit"],
    ["price", "Price"],
    ["currency", "Cur"],
    ["supplier", "Supplier"],
    ["validFrom", "Valid from"],
  ],
  sizes: [
    ["block", "Block"],
    ["pointOfMeasure", "Point of measure"],
    ["size", "Size"],
    ["value", "Value"],
    ["unit", "Unit"],
    ["tolerance", "Tol."],
  ],
  sales: [
    ["style", "Style"],
    ["launchDate", "Launch"],
    ["week", "Week"],
    ["units", "Units"],
    ["size", "Size"],
  ],
};

const NUMERIC = new Set(["moq", "leadTimeWeeks", "price", "value", "tolerance", "week", "units"]);

/** Units per week since launch, summed over every style in a sales-history preview (only rows that parse). */
function weeklyUnits(preview: ImportPreview): number[] {
  const byWeek = new Map<number, number>();
  for (const r of preview.rows) {
    const w = Number(r.week);
    const u = Number(r.units);
    if (Number.isFinite(w) && Number.isFinite(u)) byWeek.set(w, (byWeek.get(w) ?? 0) + u);
  }
  return [...byWeek.entries()].sort((a, b) => a[0] - b[0]).map(([, u]) => u);
}

export function PreviewTable({ preview, max = 40 }: { preview: ImportPreview; max?: number }) {
  const cols = PREVIEW_COLUMNS[preview.kind];
  const byRow = new Map<number, string[]>();
  for (const i of preview.issues) {
    if (i.row > 0 && i.level === "error")
      byRow.set(i.row, [...(byRow.get(i.row) ?? []), `${i.field ? `${i.field}: ` : ""}${i.message}`]);
  }
  const fileIssues = preview.issues.filter((i) => i.row === 0);
  const rowIssues = preview.issues.filter((i) => i.row > 0);
  const errors = preview.issues.filter((i) => i.level === "error").length;
  const warnings = preview.issues.length - errors;
  const weeks = preview.kind === "sales" ? weeklyUnits(preview) : [];
  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center gap-2">
        <span className="mr-1 font-mono text-small break-all text-fg">{preview.filename}</span>
        <Badge tone="neutral">
          {preview.rows.length} row{preview.rows.length === 1 ? "" : "s"} read
        </Badge>
        <Badge tone="ok">{preview.validRows} valid</Badge>
        {errors > 0 && (
          <Badge tone="bad">
            {errors} error{errors === 1 ? "" : "s"}
          </Badge>
        )}
        {warnings > 0 && (
          <Badge tone="warn">
            {warnings} warning{warnings === 1 ? "" : "s"}
          </Badge>
        )}
        {preview.ignoredColumns.length > 0 && <Badge tone="faint">ignored: {preview.ignoredColumns.join(", ")}</Badge>}
      </div>
      {fileIssues.map((i, k) => (
        <InlineAlert key={k} tone="bad" title="The file can't be imported">
          {i.message}
        </InlineAlert>
      ))}
      {weeks.length > 1 && (
        <div className="rounded-panel bg-paper-2/60 p-4">
          <div className="flex items-baseline justify-between gap-3">
            <Label as="p">Units per week since launch · all styles in the file</Label>
            <span className="font-mono text-micro text-fg-faint">{weeks.length} weeks</span>
          </div>
          <Sparkline className="mt-3" height={48} values={weeks} label="Units per week since launch" tone="accent" />
        </div>
      )}
      {preview.rows.length > 0 && (
        <Table caption={`Preview of ${preview.filename}`} dense className="max-h-[26rem] overflow-y-auto">
          <THead>
            <Tr>
              <Th>#</Th>
              {byRow.size > 0 && <Th>Check</Th>}
              {cols.map(([key, label]) => (
                <Th key={label} numeric={NUMERIC.has(key)}>
                  {label}
                </Th>
              ))}
            </Tr>
          </THead>
          <TBody>
            {preview.rows.slice(0, max).map((r) => {
              const n = Number(r._row);
              const errs = byRow.get(n);
              return (
                <Tr key={n} className={errs ? "bg-bad-soft hover:bg-bad-soft" : undefined}>
                  <Td className={cx("font-mono text-micro", errs ? "text-bad" : "text-fg-faint")}>{n}</Td>
                  {byRow.size > 0 && (
                    <Td className="min-w-[12rem] text-micro">
                      {errs ? (
                        <span className="text-bad">{errs.join(" · ")}</span>
                      ) : (
                        <span className="text-ok">ok</span>
                      )}
                    </Td>
                  )}
                  {cols.map(([key]) => (
                    <Td
                      key={key}
                      numeric={NUMERIC.has(key)}
                      className={cx("max-w-[16rem] break-words", !NUMERIC.has(key) && "min-w-[8rem] text-fg-muted")}
                    >
                      {r[key] === null || r[key] === undefined || r[key] === "" ? (
                        <span className="text-fg-faint">-</span>
                      ) : (
                        String(r[key])
                      )}
                    </Td>
                  ))}
                </Tr>
              );
            })}
          </TBody>
        </Table>
      )}
      {preview.rows.length > max && (
        <p className="text-micro text-fg-faint">
          Showing the first {max} of {preview.rows.length} rows.
        </p>
      )}
      {rowIssues.length > 0 && (
        <ul className="max-h-48 overflow-auto rounded-panel border border-line text-small">
          {rowIssues.map((i, k) => (
            <li key={k} className="flex gap-3 border-t border-line px-4 py-2 first:border-t-0">
              <span
                className={cx(
                  "shrink-0 font-mono text-micro leading-5",
                  i.level === "error" ? "text-bad" : "text-warn",
                )}
              >
                row {i.row}
              </span>
              <span className="text-fg-muted">
                {i.field && <span className="font-medium text-fg">{i.field}: </span>}
                {i.message}
              </span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

/** Upload -> preview with validation -> import (replace / append). */
export function ImportPanel({
  kind,
  noun,
  onCommitted,
  confirmNote,
}: {
  kind: ImportKind;
  noun: string;
  onCommitted: (p: ImportPreview) => void;
  confirmNote?: ReactNode;
}) {
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<ImportPreview | null>(null);
  const [mode, setMode] = useState<"replace" | "append">("replace");
  const [busy, setBusy] = useState<"read" | "commit" | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState<string | null>(null);

  const read = async (f: File) => {
    setFile(f);
    setBusy("read");
    setError(null);
    setDone(null);
    try {
      setPreview(await importTable(kind, f, { commit: false }));
    } catch (e) {
      setPreview(null);
      setError(errorMessage(e));
    } finally {
      setBusy(null);
    }
  };

  const commit = async () => {
    if (!file) return;
    setBusy("commit");
    setError(null);
    try {
      const p = await importTable(kind, file, { commit: true, mode });
      setPreview(p);
      if (p.committed) {
        setDone(p.provenance?.label ?? "Imported.");
        setPreview(null);
        setFile(null);
        onCommitted(p);
      }
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setBusy(null);
    }
  };

  const errors = preview?.issues.filter((i) => i.level === "error").length ?? 0;
  return (
    <div className="flex flex-col gap-4">
      <DropZone
        accept=".csv,.tsv,.txt,.xlsx,.xlsm"
        busy={busy === "read"}
        onFile={read}
        label={`Drop your ${noun} (CSV or XLSX), or click to choose`}
        hint="First row = headers · nothing is saved until you import"
      />
      <div className="flex flex-wrap items-center justify-between gap-2">
        <a href={templateUrl(kind)} download className={buttonClass({ variant: "ghost", size: "sm" })}>
          <IconArrowDown size={14} /> CSV template (headers only)
        </a>
      </div>
      {error && (
        <InlineAlert tone="bad" title="Couldn't read the file">
          {error}
        </InlineAlert>
      )}
      {done && (
        <p role="status" className="flex items-center gap-2 text-small text-ok">
          <IconCheck size={14} strokeWidth={2.4} /> {done}
        </p>
      )}
      {preview && (
        <>
          <PreviewTable preview={preview} />
          <div className="flex flex-col gap-4 rounded-panel border border-line bg-surface p-4 sm:p-5 md:flex-row md:items-center md:justify-between">
            <div className="flex min-w-0 flex-col gap-2">
              <Segmented
                label="Import mode"
                size="sm"
                value={mode}
                onChange={setMode}
                options={[
                  { value: "replace", label: `Replace the ${noun}` },
                  { value: "append", label: "Add to it" },
                ]}
              />
              {confirmNote}
              {errors > 0 && (
                <p className="text-small text-bad">
                  Fix the {errors} error{errors === 1 ? "" : "s"} in the file and drop it again.
                </p>
              )}
            </div>
            <div className="flex shrink-0 gap-2">
              <Button
                variant="ghost"
                onClick={() => {
                  setPreview(null);
                  setFile(null);
                }}
              >
                Discard
              </Button>
              <Button onClick={commit} disabled={errors > 0 || preview.validRows === 0} loading={busy === "commit"}>
                Import {preview.validRows} row{preview.validRows === 1 ? "" : "s"}
              </Button>
            </div>
          </div>
        </>
      )}
    </div>
  );
}
