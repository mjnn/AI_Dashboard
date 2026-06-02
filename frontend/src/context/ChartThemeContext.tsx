import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import {
  CHART_THEME_STORAGE_KEY,
  CUSTOM_PALETTE_ID,
  DEFAULT_CUSTOM_COLORS,
  DEFAULT_PALETTE_ID,
  MAX_CUSTOM_COLORS,
  MIN_CUSTOM_COLORS,
  resolvePaletteColors,
  CHART_PALETTE_PRESETS,
  type ChartPalettePreset,
} from "../theme/chartPalettes";

interface StoredTheme {
  presetId: string;
  customColors: string[];
}

interface ChartThemeContextValue {
  presetId: string;
  customColors: string[];
  colors: string[];
  setPresetId: (id: string) => void;
  setCustomColors: (colors: string[]) => void;
  updateCustomColor: (index: number, color: string) => void;
  addCustomColor: () => void;
  removeCustomColor: (index: number) => void;
  presets: ChartPalettePreset[];
}

const ChartThemeContext = createContext<ChartThemeContextValue | null>(null);

function loadStoredTheme(): StoredTheme {
  try {
    const raw = localStorage.getItem(CHART_THEME_STORAGE_KEY);
    if (!raw) {
      return { presetId: DEFAULT_PALETTE_ID, customColors: [...DEFAULT_CUSTOM_COLORS] };
    }
    const parsed = JSON.parse(raw) as StoredTheme;
    return {
      presetId: parsed.presetId ?? DEFAULT_PALETTE_ID,
      customColors: Array.isArray(parsed.customColors)
        ? parsed.customColors
        : [...DEFAULT_CUSTOM_COLORS],
    };
  } catch {
    return { presetId: DEFAULT_PALETTE_ID, customColors: [...DEFAULT_CUSTOM_COLORS] };
  }
}

function persistTheme(theme: StoredTheme) {
  localStorage.setItem(CHART_THEME_STORAGE_KEY, JSON.stringify(theme));
}

export function ChartThemeProvider({ children }: { children: ReactNode }) {
  const [stored, setStored] = useState<StoredTheme>(loadStoredTheme);

  const colors = useMemo(
    () => resolvePaletteColors(stored.presetId, stored.customColors),
    [stored.presetId, stored.customColors]
  );

  const commit = useCallback((next: StoredTheme) => {
    setStored(next);
    persistTheme(next);
  }, []);

  const setPresetId = useCallback(
    (id: string) => {
      commit({ ...stored, presetId: id });
    },
    [commit, stored]
  );

  const setCustomColors = useCallback(
    (customColors: string[]) => {
      commit({ presetId: CUSTOM_PALETTE_ID, customColors });
    },
    [commit]
  );

  const updateCustomColor = useCallback(
    (index: number, color: string) => {
      const next = [...stored.customColors];
      next[index] = color;
      commit({ presetId: CUSTOM_PALETTE_ID, customColors: next });
    },
    [commit, stored.customColors]
  );

  const addCustomColor = useCallback(() => {
    if (stored.customColors.length >= MAX_CUSTOM_COLORS) {
      return;
    }
    const next = [...stored.customColors, "#6366F1"];
    commit({ presetId: CUSTOM_PALETTE_ID, customColors: next });
  }, [commit, stored.customColors]);

  const removeCustomColor = useCallback(
    (index: number) => {
      if (stored.customColors.length <= MIN_CUSTOM_COLORS) {
        return;
      }
      const next = stored.customColors.filter((_, i) => i !== index);
      commit({ presetId: CUSTOM_PALETTE_ID, customColors: next });
    },
    [commit, stored.customColors]
  );

  const value = useMemo(
    () => ({
      presetId: stored.presetId,
      customColors: stored.customColors,
      colors,
      setPresetId,
      setCustomColors,
      updateCustomColor,
      addCustomColor,
      removeCustomColor,
      presets: CHART_PALETTE_PRESETS,
    }),
    [
      stored.presetId,
      stored.customColors,
      colors,
      setPresetId,
      setCustomColors,
      updateCustomColor,
      addCustomColor,
      removeCustomColor,
    ]
  );

  return (
    <ChartThemeContext.Provider value={value}>{children}</ChartThemeContext.Provider>
  );
}

export function useChartTheme(): ChartThemeContextValue {
  const ctx = useContext(ChartThemeContext);
  if (!ctx) {
    throw new Error("useChartTheme must be used within ChartThemeProvider");
  }
  return ctx;
}
