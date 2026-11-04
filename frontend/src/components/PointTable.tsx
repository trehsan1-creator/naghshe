import { useMemo, useState } from "react";
import {
  flexRender,
  getCoreRowModel,
  getPaginationRowModel,
  getSortedRowModel,
  useReactTable,
  type ColumnDef,
  type SortingState,
} from "@tanstack/react-table";
import {
  ArrowDown,
  ArrowUp,
  CheckCheck,
  ChevronLeft,
  ChevronRight,
  Search,
  ShieldCheck,
  Table2,
  XCircle,
} from "lucide-react";
import { useWorkspace } from "../store/workspace";
import type { PointStatus, SurveyPoint } from "../lib/types";
import { SeverityDot, fmt, fmtInt } from "./ui";

const STATUSES: PointStatus[] = ["RAW", "VALIDATED", "APPROVED", "REJECTED"];

export default function PointTable() {
  const points = useWorkspace((s) => s.points);
  const pointsTotal = useWorkspace((s) => s.pointsTotal);
  const statusFilter = useWorkspace((s) => s.statusFilter);
  const setStatusFilter = useWorkspace((s) => s.setStatusFilter);
  const search = useWorkspace((s) => s.search);
  const setSearch = useWorkspace((s) => s.setSearch);
  const refreshPoints = useWorkspace((s) => s.refreshPoints);
  const selected = useWorkspace((s) => s.selectedPoint);
  const selectPoint = useWorkspace((s) => s.selectPoint);
  const updateStatus = useWorkspace((s) => s.updateStatus);
  const [sorting, setSorting] = useState<SortingState>([]);
  const [selection, setSelection] = useState<Record<string, boolean>>({});

  const selectedIds = useMemo(() => Object.keys(selection).filter((id) => selection[id]), [selection]);

  const columns = useMemo<ColumnDef<SurveyPoint>[]>(
    () => [
      {
        id: "select",
        header: ({ table }) => (
          <input
            type="checkbox"
            className="accent-cyan"
            checked={table.getIsAllPageRowsSelected()}
            onChange={table.getToggleAllPageRowsSelectedHandler()}
            onClick={(event) => event.stopPropagation()}
          />
        ),
        cell: ({ row }) => (
          <input
            type="checkbox"
            className="accent-cyan"
            checked={row.getIsSelected()}
            onChange={row.getToggleSelectedHandler()}
            onClick={(event) => event.stopPropagation()}
          />
        ),
        size: 26,
        enableSorting: false,
      },
      {
        accessorKey: "point_number",
        header: "نقطه",
        cell: (info) => <span className="font-mono text-ink">{info.getValue() as string}</span>,
        size: 70,
      },
      {
        accessorKey: "code",
        header: "کد",
        cell: (info) => <span className="font-mono text-cyan/90">{(info.getValue() as string) || "—"}</span>,
        size: 96,
      },
      {
        accessorKey: "easting",
        header: "X (easting)",
        cell: (info) => <span className="tabular">{fmt(info.getValue() as number)}</span>,
        size: 104,
      },
      {
        accessorKey: "northing",
        header: "Y (northing)",
        cell: (info) => <span className="tabular">{fmt(info.getValue() as number)}</span>,
        size: 104,
      },
      {
        accessorKey: "elevation",
        header: "Z (m)",
        cell: (info) => <span className="tabular">{fmt(info.getValue() as number | null)}</span>,
        size: 78,
      },
      {
        accessorKey: "layer",
        header: "لایه",
        cell: (info) => <span className="font-mono text-[10px] text-muted">{(info.getValue() as string) || "—"}</span>,
        size: 110,
      },
      {
        accessorKey: "description",
        header: "شرح",
        cell: (info) => (
          <span className="text-[11px] text-muted truncate">{(info.getValue() as string) || "—"}</span>
        ),
        size: 160,
      },
      {
        accessorKey: "status",
        header: "وضعیت",
        cell: (info) => {
          const status = info.getValue() as string;
          return <span className={`status-${status} font-mono text-[10px] uppercase`}>{status}</span>;
        },
        size: 88,
      },
      {
        id: "qa",
        header: "QA",
        accessorFn: (row) => row.qa_severity ?? "ok",
        cell: (info) => {
          const row = info.row.original;
          return (
            <span className="flex items-center gap-1.5" title={row.qa_flags ?? ""}>
              <SeverityDot severity={row.qa_severity} />
              <span className="text-[9px] font-mono text-muted">
                {row.qa_flags ? (JSON.parse(row.qa_flags) as string[]).join(",") : ""}
              </span>
            </span>
          );
        },
        size: 120,
      },
      {
        accessorKey: "version",
        header: "v",
        cell: (info) => <span className="font-mono text-[10px] text-muted">{info.getValue() as number}</span>,
        size: 34,
      },
    ],
    [],
  );

  const table = useReactTable({
    data: points,
    columns,
    state: { sorting, rowSelection: selection },
    onSortingChange: setSorting,
    onRowSelectionChange: setSelection,
    getRowId: (row) => row.id,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
    getPaginationRowModel: getPaginationRowModel(),
    initialState: { pagination: { pageSize: 200, pageIndex: 0 } },
  });

  const toggleStatus = (status: PointStatus) => {
    const next = statusFilter.includes(status)
      ? statusFilter.filter((s) => s !== status)
      : [...statusFilter, status];
    setStatusFilter(next);
  };

  const page = table.getState().pagination.pageIndex;
  const pageCount = Math.max(table.getPageCount(), 1);

  return (
    <div className="h-full flex flex-col min-h-0">
      <div className="h-9 shrink-0 flex items-center gap-2 px-2 border-b border-edge">
        <Table2 size={12} className="text-muted" />
        <span className="text-[10px] uppercase tracking-[0.14em] text-muted">جدول نقاط برداشت</span>

        <div className="flex items-center gap-0.5 ms-2">
          {STATUSES.map((status) => {
            const active = statusFilter.includes(status);
            const count = points.filter((p) => p.status === status).length;
            return (
              <button
                key={status}
                onClick={() => toggleStatus(status)}
                className={`h-5 px-1.5 rounded border text-[9px] font-mono uppercase tracking-wide transition-colors ${
                  active
                    ? `status-${status} border-current bg-white/5`
                    : "border-edge text-muted/70 hover:text-muted"
                }`}
                title={`Filter ${status}`}
              >
                {status.slice(0, 4)} {count}
              </button>
            );
          })}
        </div>

        <div className="relative ms-2">
          <Search size={11} className="absolute start-1.5 top-1/2 -translate-y-1/2 text-muted" />
          <input
            className="field !h-6 !w-44 !ps-6 !text-[10px]"
            placeholder="point, code, description…"
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter") void refreshPoints();
            }}
          />
        </div>

        <div className="ms-auto flex items-center gap-1">
          <span className="text-[9px] font-mono text-muted me-1">
            {fmtInt(points.length)} / {fmtInt(pointsTotal)} rows
            {selectedIds.length > 0 && <span className="text-cyan"> · {selectedIds.length} selected</span>}
          </span>
          <button
            className="btn-ghost !h-6 !px-1.5 text-[10px]"
            onClick={() => void updateStatus("APPROVED", selectedIds.length ? selectedIds : undefined)}
            title={selectedIds.length ? "تأیید نقاط انتخاب‌شده" : "تأیید همهٔ نقاط فیلترشده"}
          >
            <CheckCheck size={11} /> Approve
          </button>
          <button
            className="btn-ghost !h-6 !px-1.5 text-[10px]"
            onClick={() => void updateStatus("VALIDATED", selectedIds.length ? selectedIds : undefined)}
            title="علامت‌گذاری به‌عنوان اعتبارسنجی‌شده"
          >
            <ShieldCheck size={11} /> Validate
          </button>
          <button
            className="btn-ghost !h-6 !px-1.5 text-[10px] hover:!text-danger"
            onClick={() => void updateStatus("REJECTED", selectedIds.length ? selectedIds : undefined)}
            title="رد نقاط انتخاب‌شده"
          >
            <XCircle size={11} /> Reject
          </button>
        </div>
      </div>

      <div className="flex-1 min-h-0 overflow-auto">
        <table className="w-full text-[11px] border-collapse">
          <thead className="sticky top-0 z-10 bg-panel2">
            {table.getHeaderGroups().map((headerGroup) => (
              <tr key={headerGroup.id} className="border-b border-edge">
                {headerGroup.headers.map((header) => (
                  <th
                    key={header.id}
                    style={{ width: header.getSize() }}
                    className="text-start font-medium text-[9px] uppercase tracking-[0.1em] text-muted px-2 py-1 whitespace-nowrap select-none cursor-pointer hover:text-ink"
                    onClick={header.column.getToggleSortingHandler()}
                  >
                    <span className="inline-flex items-center gap-0.5">
                      {flexRender(header.column.columnDef.header, header.getContext())}
                      {header.column.getIsSorted() === "asc" && <ArrowUp size={9} />}
                      {header.column.getIsSorted() === "desc" && <ArrowDown size={9} />}
                    </span>
                  </th>
                ))}
              </tr>
            ))}
          </thead>
          <tbody>
            {table.getRowModel().rows.map((row) => {
              const isSelected = selected?.id === row.original.id;
              return (
                <tr
                  key={row.id}
                  onClick={() => selectPoint(row.original)}
                  className={`border-b border-edge/40 cursor-pointer transition-colors ${
                    isSelected ? "bg-cyan/10" : "hover:bg-panel2/60"
                  }`}
                >
                  {row.getVisibleCells().map((cell) => (
                    <td key={cell.id} className="px-2 py-[3px] whitespace-nowrap overflow-hidden text-ellipsis">
                      {flexRender(cell.column.columnDef.cell, cell.getContext())}
                    </td>
                  ))}
                </tr>
              );
            })}
            {points.length === 0 && (
              <tr>
                <td colSpan={columns.length} className="px-3 py-6 text-center text-[11px] text-muted">
                  No points match the current filter.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      <div className="h-7 shrink-0 flex items-center gap-2 px-2 border-t border-edge text-[9px] text-muted font-mono">
        <span>
          page {page + 1} / {pageCount}
        </span>
        <div className="ms-auto flex items-center gap-1">
          <button className="btn-ghost !h-5 !px-1" onClick={() => table.previousPage()} disabled={!table.getCanPreviousPage()}>
            <ChevronLeft size={12} />
          </button>
          <button className="btn-ghost !h-5 !px-1" onClick={() => table.nextPage()} disabled={!table.getCanNextPage()}>
            <ChevronRight size={12} />
          </button>
        </div>
      </div>
    </div>
  );
}
