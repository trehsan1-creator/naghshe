import { useNavigate } from "react-router-dom";
import { Compass } from "lucide-react";

export default function NotFound() {
  const navigate = useNavigate();
  return (
    <div className="h-full flex flex-col items-center justify-center gap-3">
      <Compass size={30} className="text-cyan/70" />
      <div className="text-sm">این مسیر در نقشهٔ برنامه وجود ندارد</div>
      <div className="text-[11px] text-muted font-mono">۴۰۴ · مسیر موردنظر پیدا نشد</div>
      <button className="btn-primary mt-2" onClick={() => navigate("/")}>
        Back to project hub
      </button>
    </div>
  );
}
