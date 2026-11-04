import { useWorkspace } from "../store/workspace";
import { Spinner } from "./ui";

/** Slim, non-blocking progress strip pinned to the bottom of the shell. */
export default function BusyBar() {
  const busy = useWorkspace((s) => s.busy);
  if (!busy) return null;
  return (
    <div className="absolute bottom-0 start-0 end-0 h-8 z-40 flex items-center gap-2 px-3 bg-panel2/95 border-t border-cyan/30 backdrop-blur">
      <Spinner />
      <span className="text-[11px] text-cyan font-mono tracking-wide">{busy}</span>
      <div className="flex-1 h-[2px] overflow-hidden rounded bg-edge">
        <div className="h-full w-1/3 bg-cyan/70 animate-[slide_1.1s_ease-in-out_infinite]" />
      </div>
      <style>{`@keyframes slide{0%{transform:translateX(-100%)}100%{transform:translateX(300%)}}`}</style>
    </div>
  );
}
