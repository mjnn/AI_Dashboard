export interface ChartPalettePreset {
  id: string;
  name: string;
  colors: string[];
}

export const CHART_PALETTE_PRESETS: ChartPalettePreset[] = [
  {
    id: "vivid",
    name: "鲜明多彩",
    colors: [
      "#007AFF",
      "#FF9500",
      "#34C759",
      "#FF3B30",
      "#5856D6",
      "#AF52DE",
      "#FF2D55",
      "#00C7BE",
    ],
  },
  {
    id: "sunset",
    name: "落日暖色",
    colors: [
      "#FF6B6B",
      "#FFA94D",
      "#FFD43B",
      "#F06595",
      "#845EF7",
      "#22B8CF",
      "#E8590C",
      "#C2255C",
    ],
  },
  {
    id: "forest",
    name: "森林自然",
    colors: [
      "#2F9E44",
      "#51CF66",
      "#94D82D",
      "#F08C00",
      "#099268",
      "#40C057",
      "#82C91E",
      "#E67700",
    ],
  },
  {
    id: "aurora",
    name: "极光渐变",
    colors: [
      "#9775FA",
      "#748FFC",
      "#3BC9DB",
      "#38D9A9",
      "#FFC078",
      "#FF8787",
      "#DA77F2",
      "#4DABF7",
    ],
  },
  {
    id: "business",
    name: "商务稳重",
    colors: [
      "#495057",
      "#228BE6",
      "#40C057",
      "#FAB005",
      "#BE4BDB",
      "#FD7E14",
      "#15AABF",
      "#868E96",
    ],
  },
  {
    id: "custom",
    name: "自定义",
    colors: [],
  },
];

export const DEFAULT_PALETTE_ID = "vivid";
export const CUSTOM_PALETTE_ID = "custom";
export const CHART_THEME_STORAGE_KEY = "ai-dashboard-chart-theme";
export const MIN_CUSTOM_COLORS = 3;
export const MAX_CUSTOM_COLORS = 12;

export const DEFAULT_CUSTOM_COLORS = [
  "#6366F1",
  "#F97316",
  "#10B981",
  "#EF4444",
  "#8B5CF6",
  "#06B6D4",
];

export function getPresetById(id: string): ChartPalettePreset | undefined {
  return CHART_PALETTE_PRESETS.find((item) => item.id === id);
}

export function resolvePaletteColors(
  presetId: string,
  customColors: string[]
): string[] {
  if (presetId === CUSTOM_PALETTE_ID) {
    const valid = customColors.filter(isValidHexColor);
    return valid.length >= MIN_CUSTOM_COLORS ? valid : DEFAULT_CUSTOM_COLORS;
  }
  const preset = getPresetById(presetId);
  return preset?.colors.length ? preset.colors : CHART_PALETTE_PRESETS[0].colors;
}

export function isValidHexColor(value: string): boolean {
  return /^#([0-9A-Fa-f]{6}|[0-9A-Fa-f]{3})$/.test(value.trim());
}

/** 热力图渐变色：基于主题首色生成浅→深 */
export function heatmapGradient(primary: string): [string, string, string] {
  const rgb = hexToRgb(primary);
  if (!rgb) {
    return ["#F3F4F6", "#6366F1", "#312E81"];
  }
  const light = mixRgb(rgb, { r: 255, g: 255, b: 255 }, 0.88);
  const dark = mixRgb(rgb, { r: 0, g: 0, b: 0 }, 0.35);
  return [rgbToHex(light), primary, rgbToHex(dark)];
}

function hexToRgb(hex: string): { r: number; g: number; b: number } | null {
  const normalized = hex.replace("#", "");
  const full =
    normalized.length === 3
      ? normalized
          .split("")
          .map((c) => c + c)
          .join("")
      : normalized;
  if (!/^[0-9A-Fa-f]{6}$/.test(full)) {
    return null;
  }
  return {
    r: parseInt(full.slice(0, 2), 16),
    g: parseInt(full.slice(2, 4), 16),
    b: parseInt(full.slice(4, 6), 16),
  };
}

function mixRgb(
  a: { r: number; g: number; b: number },
  b: { r: number; g: number; b: number },
  weight: number
) {
  return {
    r: Math.round(a.r * (1 - weight) + b.r * weight),
    g: Math.round(a.g * (1 - weight) + b.g * weight),
    b: Math.round(a.b * (1 - weight) + b.b * weight),
  };
}

function rgbToHex(rgb: { r: number; g: number; b: number }): string {
  const part = (n: number) => n.toString(16).padStart(2, "0");
  return `#${part(rgb.r)}${part(rgb.g)}${part(rgb.b)}`;
}
