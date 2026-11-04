/** واژه‌نامه فارسی سامانه — برچسب‌های دامنه، کدهای کیفیت و اصطلاحات مهندسی. */

export const STATUS_FA: Record<string, string> = {
  RAW: "خام",
  VALIDATED: "اعتبارسنجی‌شده",
  APPROVED: "تأییدشده",
  REJECTED: "ردشده",
  CURRENT: "به‌روز",
  OUTDATED: "منقضی",
  committed: "ثبت‌شده",
  analysed: "تحلیل‌شده",
  uploaded: "بارگذاری‌شده",
  DRAFT: "پیش‌نویس",
  FIELDWORK: "عملیات میدانی",
  PROCESSING: "در پردازش",
  QAQC: "کنترل کیفیت",
  ARCHIVED: "بایگانی",
};

export const SEVERITY_FA: Record<string, string> = {
  error: "خطا",
  warning: "هشدار",
  info: "اطلاع",
  ok: "سالم",
};

export const KIND_FA: Record<string, string> = {
  surface: "سطح",
  contours: "خطوط تراز",
  volume: "احجام",
  profile: "پروفیل",
  cross_sections: "مقاطع عرضی",
  dxf: "خروجی DXF",
  report: "گزارش",
  linework: "خطوط نقشه",
  point: "نقطه",
};

export const CODE_KIND_FA: Record<string, string> = {
  point: "نقطه",
  block: "بلوک",
  line: "خط",
  polygon: "چندضلعی",
};

/** کدهای کنترل کیفیت موتور اعتبارسنجی → عنوان و توضیح فارسی. */
export const QA_CODE_FA: Record<string, { title: string; hint?: string }> = {
  axis_swap: {
    title: "احتمال جابه‌جایی محورها",
    hint: "مقادیر شرقی و شمالی برعکس وارد شده‌اند؛ از گزینه «جابه‌جایی X و Y» در ویزارد ورود داده استفاده کنید.",
  },
  duplicate_coordinates: {
    title: "مختصات تکراری",
    hint: "دو یا چند نقطه در بازه تحمل یکسان هستند؛ نقطه تکراری را رد یا ادغام کنید.",
  },
  duplicate_point_number: {
    title: "شماره نقطه تکراری",
    hint: "شماره نقطه باید یکتا باشد؛ در ویزارد ورود داده سیاست «جایگزینی» را انتخاب کنید.",
  },
  elevation_anomaly: {
    title: "ارتفاع پرت",
    hint: "اختلاف ارتفاع نسبت به میانه مطلق (MAD) بیش از حد آستانه است.",
  },
  elevation_range: {
    title: "دامنه ارتفاع غیرعادی",
    hint: "اختلاف بیشینه و کمینه ارتفاع فراتر از محدوده مورد انتظار پروژه است.",
  },
  elevation_spike: {
    title: "پرش ارتفاعی موضعی",
    hint: "اختلاف ارتفاع با نقاط همسایه بیش از آستانه گام محلی است؛ احتمال خطای تیرک یا کد ارتفاعی.",
  },
  elevation_statistics: {
    title: "آمار توصیفی ارتفاع",
    hint: "خلاصه توزیع ارتفاع برای کنترل اولیه کیفیت داده.",
  },
  unknown_code: {
    title: "کد برداشت ناشناخته",
    hint: "کد در کتابخانه کدهای پروژه تعریف نشده است؛ در بخش «کتابخانه کدها» آن را اضافه کنید.",
  },
  projection_warning: {
    title: "هشدار سیستم تصویر",
    hint: "مختصات خارج از محدوده کاربرد سیستم تصویر پروژه است.",
  },
  outside_boundary: {
    title: "خارج از محدوده",
    hint: "نقطه بیرون از مرز سطح مثلث‌بندی قرار گرفته است.",
  },
  tin_duplicate_vertices: {
    title: "رأس‌های منطبق در TIN",
    hint: "نقاط کاملاً منطبق پیش از مثلث‌بندی ادغام شدند (بالاترین ارتفاع حفظ شده است).",
  },
  breakline_not_closed: {
    title: "خط شکست باز",
    hint: "خط شکست بسته نشده است؛ برای مثلث‌بندی مقید بهتر است حلقه بسته باشد.",
  },
  low_point_density: {
    title: "تراکم پایین نقاط",
    hint: "تراکم نقاط برای تولید خطوط تراز با این فاصله مناسب نیست.",
  },
};

export function flagTitle(code: string): string {
  return QA_CODE_FA[code]?.title ?? "یافته کنترل کیفیت";
}

export function flagHint(code: string): string | undefined {
  return QA_CODE_FA[code]?.hint;
}

/** نام فارسی لایه‌های استاندارد CAD. */
export const LAYER_FA: Record<string, string> = {
  "S-POINT": "نقاط برداشت",
  "S-ELEV": "ارتفاع نقاط",
  "S-CURB": "جدول خیابان",
  "S-SIDEWALK": "پیاده‌رو",
  "S-ROAD": "سطح سواره‌رو",
  "S-TREE": "درختان",
  "S-UTILITY": "تأسیسات",
  "S-CENTRELINE": "محور مسیر",
  "S-BOUNDARY": "مرز محدوده",
  "S-CONTOUR-MAJOR": "خطوط تراز اصلی",
  "S-CONTOUR-MINOR": "خطوط تراز فرعی",
  "S-BREAKLINE": "خط شکست",
};

export function layerLabel(layer: string): string {
  return LAYER_FA[layer] ? `${LAYER_FA[layer]}` : layer;
}

/** ارقام لاتین با جداکننده هزارگان — استاندارد گزارش‌های مهندسی فارسی. */
export const num = (value: number | null | undefined, digits = 3) =>
  value === null || value === undefined || Number.isNaN(value)
    ? "—"
    : value.toLocaleString("en-GB", { minimumFractionDigits: digits, maximumFractionDigits: digits });

export const int = (value: number | null | undefined) =>
  value === null || value === undefined ? "—" : Math.round(value).toLocaleString("en-GB");
