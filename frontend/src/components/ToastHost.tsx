import { AlertTriangle, CheckCircle2, Info, X } from "lucide-react";
import { useWorkspace } from "../store/workspace";

export default function ToastHost() {
  const toasts = useWorkspace((s) => s.toasts);
  const dismiss = useWorkspace((s) => s.dismissToast);

  return (
    <div className="fixed bottom-4 end-4 z-[60] flex flex-col gap-2 max-w-sm">
      {toasts.map((toast) => {
        const tones = {
          info: { border: "border-cyan/40", icon: <Info size={14} className="text-cyan" /> },
          success: { border: "border-lime/40", icon: <CheckCircle2 size={14} className="text-lime" /> },
          error: { border: "border-danger/50", icon: <AlertTriangle size={14} className="text-danger" /> },
        }[toast.kind];
        return (
          <div
            key={toast.id}
            className={`panel ${tones.border} shadow-xl px-3 py-2 flex items-start gap-2 text-xs bg-panel2/95 backdrop-blur`}
          >
            <span className="mt-0.5">{tones.icon}</span>
            <span className="flex-1 leading-relaxed break-words">{toast.message}</span>
            <button className="text-muted hover:text-ink" onClick={() => dismiss(toast.id)}>
              <X size={12} />
            </button>
          </div>
        );
      })}
    </div>
  );
}
