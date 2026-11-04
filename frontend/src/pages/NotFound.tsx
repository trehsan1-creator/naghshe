import { useNavigate } from "react-router-dom";
import { Compass } from "lucide-react";

export default function NotFound() {
  const navigate = useNavigate();
  return (
    <div className="h-full flex flex-col items-center justify-center gap-3">
      <Compass size={30} className="text-cyan/70" />
      <div className="text-sm">This route is not on the survey</div>
      <div className="text-[11px] text-muted font-mono">404 · no traverse found</div>
      <button className="btn-primary mt-2" onClick={() => navigate("/")}>
        Back to project hub
      </button>
    </div>
  );
}
