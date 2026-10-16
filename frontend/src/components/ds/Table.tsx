import type { HTMLAttributes, ReactNode, TdHTMLAttributes, ThHTMLAttributes } from "react";
import { cx } from "./tokens";

/**
 * Data table (BOM, measurements, quotes, sales lines). Hairline rows, small muted sentence-case heads (like `Label`), numbers right-aligned
 * in tabular figures. The wrapper is positioned (so `sr-only` cells stay inside it) and scrolls horizontally on
 * narrow screens (the page never does).
 * Compose: <Table caption="…"><THead><Tr><Th>…</Th></Tr></THead><TBody>…</TBody></Table>
 */
export function Table({
  children,
  caption,
  framed = true,
  dense,
  className,
}: {
  children: ReactNode;
  /** Visually hidden caption for screen readers (tables need a name). */
  caption?: string;
  /** Bordered panel around the table (default). Off when the table already sits in a card. */
  framed?: boolean;
  dense?: boolean;
  className?: string;
}) {
  return (
    <div
      className={cx("relative max-w-full overflow-x-auto", framed && "rounded-panel border border-line bg-surface", className)}
    >
      <table className="group/table w-full border-collapse text-left text-small" data-dense={dense || undefined}>
        {caption && <caption className="sr-only">{caption}</caption>}
        {children}
      </table>
    </div>
  );
}

export function THead({ children }: { children: ReactNode }) {
  return <thead className="border-b border-line bg-paper-2/60">{children}</thead>;
}

export function TBody({ children }: { children: ReactNode }) {
  return <tbody className="divide-y divide-line">{children}</tbody>;
}

/** A row. `selected` tints it with the accent (the chosen quote); `muted` dims it (excluded lines). */
export function Tr({ children, selected, muted, className, ...rest }: HTMLAttributes<HTMLTableRowElement> & { selected?: boolean; muted?: boolean }) {
  return (
    <tr {...rest} className={cx("transition-colors hover:bg-surface-muted", selected && "bg-accent-soft hover:bg-accent-soft", muted && "text-fg-faint", className)}>
      {children}
    </tr>
  );
}

export function Th({ children, numeric, className, ...rest }: ThHTMLAttributes<HTMLTableCellElement> & { numeric?: boolean }) {
  return (
    <th
      scope="col"
      {...rest}
      className={cx(
        "px-4 py-3 text-micro font-medium whitespace-nowrap text-fg-faint group-data-[dense]/table:py-2 first:pl-5 last:pr-5",
        numeric && "text-right",
        className,
      )}
    >
      {children}
    </th>
  );
}

export function Td({ children, numeric, className, ...rest }: TdHTMLAttributes<HTMLTableCellElement> & { numeric?: boolean }) {
  return (
    <td
      {...rest}
      className={cx(
        "px-4 py-3 align-top text-fg group-data-[dense]/table:py-2 first:pl-5 last:pr-5",
        numeric && "tabular text-right font-mono text-[0.8rem] whitespace-nowrap",
        className,
      )}
    >
      {children}
    </td>
  );
}
