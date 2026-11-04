import { useEffect, useMemo, useState } from "react";
import { Code2, Layers, Plus, Save, Trash2 } from "lucide-react";
import { api } from "../lib/api";
import { useWorkspace } from "../store/workspace";
import { Panel, StatusBadge, fmtInt } from "../components/ui";
import { aciToHex } from "../lib/plot";
import type { CodeMapping } from "../lib/types";

const KINDS: CodeMapping["kind"][] = ["point", "block", "line", "polygon"];

const BLANK: CodeMapping = {
  code: "",
  kind: "point",
  layer: "S-POINT",
  block_name: null,
  color: 7,
  description: "",
  is_breakline: false,
  enabled: true,
};

export default function CodeLibrary() {
  const project = useWorkspace((s) => s.project);
  const saveCodeMapping = useWorkspace((s) => s.saveCodeMapping);
  const toast = useWorkspace((s) => s.toast);
  const [draft, setDraft] = useState<CodeMapping>(BLANK);
  const [usage, setUsage] = useState<Record<string, number>>({});

  const mappings = useMemo(() => project?.code_mappings ?? [], [project?.code_mappings]);
  const layers = project?.layers ?? [];

  useEffect(() => {
    if (!project) return;
    api
      .listPoints(project.id, { limit: 20000 })
      .then(({ points }) => {
        const counts: Record<string, number> = {};
        for (const point of points) counts[point.code] = (counts[point.code] ?? 0) + 1;
        setUsage(counts);
      })
      .catch(() => undefined);
  }, [project?.id]);

  if (!project) return null;

  const save = async (mapping: CodeMapping) => {
    if (!mapping.code.trim()) {
      toast("error", "A field code is required");
      return;
    }
    await saveCodeMapping({ ...mapping, code: mapping.code.trim().toUpperCase() });
    setDraft(BLANK);
  };

  const remove = async (mapping: CodeMapping) => {
    if (!mapping.id) return;
    if (!window.confirm(`Delete code ${mapping.code}?`)) return;
    try {
      await api.deleteCodeMapping(project.id, mapping.id);
      toast("success", `Code ${mapping.code} deleted`);
      const refreshed = await api.getProject(project.id);
      useWorkspace.setState({ project: refreshed });
    } catch (error) {
      toast("error", `Delete failed: ${(error as Error).message}`);
    }
  };

  return (
    <div className="h-full overflow-auto">
      <div className="max-w-[1400px] mx-auto p-4 space-y-3">
        <div>
          <div className="text-[10px] uppercase tracking-[0.2em] text-cyan/80">از برداشت تا نقشه</div>
          <h1 className="text-lg font-semibold tracking-tight mt-0.5">کتابخانهٔ کدها و لایه‌های نقشه‌کشی</h1>
          <p className="text-[11px] text-muted mt-1">
            Each field code maps to a لایهٔ نقشه‌کشی, a geometry kind (point, block, line, polygon) and a
            breakline flag. These mappings drive linework generation, the TIN constraints and the DXF writer.
          </p>
        </div>

        <div className="grid grid-cols-1 xl:grid-cols-[minmax(0,1.5fr)_minmax(0,1fr)] gap-3">
          <Panel
            title="نگاشت کدهای برداشت"
            icon={<Code2 size={12} />}
            right={<span className="text-[9px] font-mono text-muted">{mappings.length} codes</span>}
          >
            <table className="w-full text-[10px]">
              <thead className="sticky top-0 bg-panel2 z-10">
                <tr className="text-[9px] uppercase tracking-[0.1em] text-muted">
                  <th className="text-start font-normal px-2 py-1">کد</th>
                  <th className="text-start font-normal px-2 py-1">نوع</th>
                  <th className="text-start font-normal px-2 py-1">لایه</th>
                  <th className="text-start font-normal px-2 py-1">بلوک</th>
                  <th className="text-center font-normal px-2 py-1">شکست</th>
                  <th className="text-end font-normal px-2 py-1">استفاده</th>
                  <th className="text-end font-normal px-2 py-1">ACI</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {mappings.map((mapping) => (
                  <tr key={mapping.id ?? mapping.code} className="border-t border-edge/40 hover:bg-panel2/50">
                    <td className="px-2 py-[3px] font-mono text-ink">{mapping.code}</td>
                    <td className="px-2 py-[3px] text-muted">{mapping.kind}</td>
                    <td className="px-2 py-[3px] font-mono text-cyan/90">{mapping.layer}</td>
                    <td className="px-2 py-[3px] font-mono text-muted">{mapping.block_name || "—"}</td>
                    <td className="px-2 py-[3px] text-center">
                      {mapping.is_breakline ? <span className="text-pink">●</span> : <span className="text-muted/40">·</span>}
                    </td>
                    <td className="px-2 py-[3px] text-end font-mono text-muted">{fmtInt(usage[mapping.code] ?? 0)}</td>
                    <td className="px-2 py-[3px] text-end">
                      <span className="inline-flex items-center gap-1 font-mono text-muted">
                        {mapping.color}
                        <span className="w-2 h-2 rounded-sm" style={{ background: aciToHex(mapping.color) }} />
                      </span>
                    </td>
                    <td className="px-1">
                      <button className="btn-ghost !h-5 !px-1 hover:!text-danger" onClick={() => void remove(mapping)}>
                        <Trash2 size={10} />
                      </button>
                    </td>
                  </tr>
                ))}
                {mappings.length === 0 && (
                  <tr>
                    <td colSpan={8} className="px-2 py-4 text-center text-[10px] text-muted">
                      No code mappings yet — add the codes used by your crews.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </Panel>

          <div className="space-y-3">
            <Panel title="افزودن یا ویرایش کد" icon={<Plus size={12} />}>
              <div className="p-2.5 space-y-2">
                <div className="grid grid-cols-2 gap-2">
                  <div>
                    <label className="label">کد برداشت *</label>
                    <input
                      className="field font-mono"
                      placeholder="CURB"
                      value={draft.code}
                      onChange={(event) => setDraft({ ...draft, code: event.target.value.toUpperCase() })}
                    />
                  </div>
                  <div>
                    <label className="label">هندسه</label>
                    <select
                      className="field"
                      value={draft.kind}
                      onChange={(event) => setDraft({ ...draft, kind: event.target.value as CodeMapping["kind"] })}
                    >
                      {KINDS.map((kind) => (
                        <option key={kind} value={kind}>
                          {kind}
                        </option>
                      ))}
                    </select>
                  </div>
                  <div>
                    <label className="label">لایهٔ نقشه‌کشی</label>
                    <input
                      className="field font-mono"
                      value={draft.layer}
                      onChange={(event) => setDraft({ ...draft, layer: event.target.value.toUpperCase() })}
                    />
                    <div className="flex flex-wrap gap-1 mt-1">
                      {["S-POINT", "S-ELEV", "S-CURB", "S-SIDEWALK", "S-ROAD", "S-TREE", "S-UTILITY", "S-CENTRELINE"].map(
                        (layer) => (
                          <button
                            key={layer}
                            className="chip hover:text-cyan"
                            onClick={() => setDraft({ ...draft, layer })}
                          >
                            {layer}
                          </button>
                        ),
                      )}
                    </div>
                  </div>
                  <div>
                    <label className="label">نام بلوک</label>
                    <input
                      className="field font-mono"
                      placeholder="TREE_SYMBOL"
                      value={draft.block_name ?? ""}
                      onChange={(event) => setDraft({ ...draft, block_name: event.target.value || null })}
                    />
                    <label className="label mt-2">رنگ ACI</label>
                    <input
                      type="number"
                      min={1}
                      max={256}
                      className="field font-mono"
                      value={draft.color}
                      onChange={(event) => setDraft({ ...draft, color: Number(event.target.value) })}
                    />
                  </div>
                </div>
                <div>
                  <label className="label">شرح</label>
                  <input
                    className="field"
                    placeholder="لبهٔ بالایی جدول"
                    value={draft.description ?? ""}
                    onChange={(event) => setDraft({ ...draft, description: event.target.value })}
                  />
                </div>
                <div className="flex items-center gap-3 text-[10px] text-muted">
                  <label className="flex items-center gap-1.5">
                    <input
                      type="checkbox"
                      className="accent-pink"
                      checked={draft.is_breakline}
                      onChange={(event) => setDraft({ ...draft, is_breakline: event.target.checked })}
                    />
                    TIN breakline
                  </label>
                  <label className="flex items-center gap-1.5">
                    <input
                      type="checkbox"
                      className="accent-cyan"
                      checked={draft.enabled}
                      onChange={(event) => setDraft({ ...draft, enabled: event.target.checked })}
                    />
                    enabled
                  </label>
                  <button className="btn-primary ms-auto !h-7" onClick={() => void save(draft)}>
                    <Save size={12} /> Save code
                  </button>
                </div>
              </div>
            </Panel>

            <Panel title="استاندارد لایه‌ها" icon={<Layers size={12} />}>
              <ul className="divide-y divide-edge/50">
                {layers.map((layer) => (
                  <li key={layer.id ?? layer.name} className="px-2.5 py-1.5 flex items-center gap-2 text-[10px]">
                    <span className="w-2 h-2 rounded-sm" style={{ background: aciToHex(layer.color) }} />
                    <span className="font-mono text-ink/90">{layer.name}</span>
                    <span className="text-muted">{layer.linetype}</span>
                    <span className="ms-auto text-muted/70 truncate max-w-[45%]">{layer.description}</span>
                  </li>
                ))}
                {layers.length === 0 && (
                  <li className="px-2.5 py-2 text-[10px] text-muted">لایه‌ای تعریف نشده است.</li>
                )}
              </ul>
            </Panel>

            <Panel title="کدهای خطوط شکست" icon={<Layers size={12} />}>
              <div className="p-2.5 flex flex-wrap gap-1">
                {(project.breakline_codes ?? []).map((code) => (
                  <span key={code} className="chip !text-[10px] text-pink border-pink/30">
                    {code}
                  </span>
                ))}
                {(project.breakline_codes ?? []).length === 0 && (
                  <span className="text-[10px] text-muted">هیچ‌کدام — خطوط جدول در ساخت شبکه مثلثی لحاظ نمی‌شوند.</span>
                )}
              </div>
              <div className="px-2.5 pb-2">
                <StatusBadge status={project.dependency_state} />
              </div>
            </Panel>
          </div>
        </div>
      </div>
    </div>
  );
}
