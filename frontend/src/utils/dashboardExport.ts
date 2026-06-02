import * as echarts from "echarts";
import html2canvas from "html2canvas";
import { jsPDF } from "jspdf";

export type DashboardExportFormat = "html" | "pdf" | "png" | "jpg";

const EXPORT_STYLES = `
  * { box-sizing: border-box; }
  body {
    margin: 0;
    padding: 24px;
    font-family: "Microsoft YaHei", "PingFang SC", "Segoe UI", sans-serif;
    color: #0f172a;
    background: #f4f7fb;
  }
  .export-root { max-width: 1200px; margin: 0 auto; }
  .narrative-banner {
    background: rgba(255,255,255,0.9);
    border: 1px solid rgba(15,23,42,0.1);
    border-radius: 14px;
    padding: 16px 20px;
    margin-bottom: 20px;
  }
  .glass-panel {
    background: rgba(255,255,255,0.9);
    border: 1px solid rgba(15,23,42,0.1);
    border-radius: 14px;
    margin-bottom: 16px;
    overflow: hidden;
  }
  h2, h3 { color: #1e293b; }
  p, li, td, th { color: #64748b; font-size: 14px; }
  img { max-width: 100%; height: auto; display: block; }
  table { width: 100%; border-collapse: collapse; }
  th, td { border: 1px solid #e2e8f0; padding: 8px; text-align: left; }
`;

function downloadBlob(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  link.click();
  URL.revokeObjectURL(url);
}

function sanitizeFilename(name: string): string {
  const cleaned = name.replace(/[<>:"/\\|?*\s]+/g, "_").slice(0, 80);
  return cleaned || "dashboard";
}

export function buildExportFilename(title: string, format: DashboardExportFormat): string {
  const stamp = new Date().toISOString().slice(0, 10);
  const base = sanitizeFilename(title);
  const ext = format === "jpg" ? "jpg" : format;
  return `${base}_${stamp}.${ext}`;
}

function replaceCanvasesWithImages(source: HTMLElement, target: HTMLElement) {
  const sourceCanvases = source.querySelectorAll("canvas");
  const targetCanvases = target.querySelectorAll("canvas");

  sourceCanvases.forEach((canvas, index) => {
    const targetCanvas = targetCanvases[index];
    if (!targetCanvas?.parentElement) {
      return;
    }
    const instance = echarts.getInstanceByDom(canvas);
    if (!instance) {
      return;
    }
    const img = document.createElement("img");
    img.src = instance.getDataURL({
      type: "png",
      pixelRatio: 2,
      backgroundColor: "#ffffff",
    });
    img.alt = "chart";
    const style = window.getComputedStyle(canvas);
    img.style.width = style.width;
    img.style.height = style.height;
    img.style.maxWidth = "100%";
    targetCanvas.parentElement.replaceChild(img, targetCanvas);
  });
}

async function waitForImages(root: HTMLElement) {
  const images = Array.from(root.querySelectorAll("img"));
  await Promise.all(
    images.map(
      (img) =>
        new Promise<void>((resolve) => {
          if (img.complete) {
            resolve();
            return;
          }
          img.onload = () => resolve();
          img.onerror = () => resolve();
        })
    )
  );
}

async function createExportSnapshot(source: HTMLElement): Promise<{
  wrapper: HTMLElement;
  cleanup: () => void;
}> {
  const wrapper = document.createElement("div");
  wrapper.style.position = "fixed";
  wrapper.style.left = "-10000px";
  wrapper.style.top = "0";
  wrapper.style.zIndex = "-1";
  wrapper.style.width = `${source.offsetWidth}px`;
  wrapper.style.background = "#f4f7fb";
  wrapper.style.padding = "16px";

  const clone = source.cloneNode(true) as HTMLElement;
  clone.classList.add("export-root");
  wrapper.appendChild(clone);
  document.body.appendChild(wrapper);

  replaceCanvasesWithImages(source, clone);
  await waitForImages(clone);

  return {
    wrapper,
    cleanup: () => wrapper.remove(),
  };
}

async function renderSnapshotCanvas(source: HTMLElement) {
  const { wrapper, cleanup } = await createExportSnapshot(source);
  try {
    return await html2canvas(wrapper, {
      scale: 2,
      useCORS: true,
      backgroundColor: "#f4f7fb",
      logging: false,
    });
  } finally {
    cleanup();
  }
}

export async function exportDashboardAsHtml(
  source: HTMLElement,
  filename: string
): Promise<void> {
  const { wrapper, cleanup } = await createExportSnapshot(source);
  try {
    const clone = wrapper.querySelector(".export-root") as HTMLElement;
    const html = `<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>${filename.replace(/\.html$/i, "")}</title>
  <style>${EXPORT_STYLES}</style>
</head>
<body>
  ${clone.outerHTML}
</body>
</html>`;
    downloadBlob(new Blob([html], { type: "text/html;charset=utf-8" }), filename);
  } finally {
    cleanup();
  }
}

export async function exportDashboardAsImage(
  source: HTMLElement,
  filename: string,
  format: "png" | "jpg"
): Promise<void> {
  const canvas = await renderSnapshotCanvas(source);
  const mime = format === "jpg" ? "image/jpeg" : "image/png";
  const quality = format === "jpg" ? 0.92 : undefined;
  const dataUrl = canvas.toDataURL(mime, quality);
  const response = await fetch(dataUrl);
  const blob = await response.blob();
  downloadBlob(blob, filename);
}

export async function exportDashboardAsPdf(
  source: HTMLElement,
  filename: string
): Promise<void> {
  const canvas = await renderSnapshotCanvas(source);
  const imgData = canvas.toDataURL("image/jpeg", 0.92);
  const pdf = new jsPDF({ orientation: "p", unit: "mm", format: "a4" });
  const pageWidth = pdf.internal.pageSize.getWidth();
  const pageHeight = pdf.internal.pageSize.getHeight();
  const imgWidth = pageWidth;
  const imgHeight = (canvas.height * imgWidth) / canvas.width;

  let heightLeft = imgHeight;
  let position = 0;

  pdf.addImage(imgData, "JPEG", 0, position, imgWidth, imgHeight);
  heightLeft -= pageHeight;

  while (heightLeft > 0) {
    position -= pageHeight;
    pdf.addPage();
    pdf.addImage(imgData, "JPEG", 0, position, imgWidth, imgHeight);
    heightLeft -= pageHeight;
  }

  pdf.save(filename);
}

export async function exportDashboard(
  source: HTMLElement,
  format: DashboardExportFormat,
  title: string
): Promise<void> {
  const filename = buildExportFilename(title, format);
  switch (format) {
    case "html":
      await exportDashboardAsHtml(source, filename);
      break;
    case "pdf":
      await exportDashboardAsPdf(source, filename);
      break;
    case "png":
      await exportDashboardAsImage(source, filename, "png");
      break;
    case "jpg":
      await exportDashboardAsImage(source, filename, "jpg");
      break;
    default:
      throw new Error(`不支持的导出格式: ${format}`);
  }
}
