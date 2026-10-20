export function downloadText(filename: string, text: string, mime = 'application/octet-stream'): void {
  const blob = new Blob([text], { type: mime });
  downloadBlob(filename, blob);
}

export function downloadBlob(filename: string, blob: Blob): void {
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

export function downloadJson(filename: string, data: unknown): void {
  downloadText(filename, JSON.stringify(data, null, 1), 'application/json');
}

/** Serialise an SVG element with the current theme colours baked in as attributes, so the file stands alone. */
export function svgToString(svg: SVGSVGElement): string {
  const clone = svg.cloneNode(true) as SVGSVGElement;
  clone.setAttribute('xmlns', 'http://www.w3.org/2000/svg');
  const srcEls = [svg, ...Array.from(svg.querySelectorAll('*'))];
  const dstEls = [clone, ...Array.from(clone.querySelectorAll('*'))];
  const props = ['fill', 'stroke', 'stroke-width', 'font-family', 'font-size', 'font-weight', 'opacity', 'stroke-dasharray', 'stroke-opacity', 'fill-opacity', 'stroke-linecap', 'text-anchor'];
  for (let i = 0; i < srcEls.length; i++) {
    const cs = window.getComputedStyle(srcEls[i]);
    const dst = dstEls[i] as Element;
    for (const p of props) {
      const v = cs.getPropertyValue(p);
      if (!v) continue;
      if (p === 'fill' && v === 'rgb(0, 0, 0)' && !dst.hasAttribute('fill') && dst.tagName !== 'text') continue;
      dst.setAttribute(p, v);
    }
    dst.removeAttribute('class');
    dst.removeAttribute('tabindex');
    dst.removeAttribute('style');
  }
  const vb = svg.viewBox.baseVal;
  const w = vb && vb.width ? vb.width : svg.clientWidth;
  const h = vb && vb.height ? vb.height : svg.clientHeight;
  clone.setAttribute('width', String(w));
  clone.setAttribute('height', String(h));
  const bg = window.getComputedStyle(svg.closest('.chart, .panel, .pane, body') ?? document.body).backgroundColor;
  const rect = document.createElementNS('http://www.w3.org/2000/svg', 'rect');
  rect.setAttribute('width', '100%'); rect.setAttribute('height', '100%'); rect.setAttribute('fill', bg);
  clone.insertBefore(rect, clone.firstChild);
  return '<?xml version="1.0" encoding="UTF-8"?>\n' + new XMLSerializer().serializeToString(clone);
}

export function downloadSvg(filename: string, svg: SVGSVGElement): void {
  downloadText(filename, svgToString(svg), 'image/svg+xml');
}

/** Rasterise the SVG at 2× and download a PNG. */
export async function downloadPng(filename: string, svg: SVGSVGElement, scale = 2): Promise<void> {
  const text = svgToString(svg);
  const vb = svg.viewBox.baseVal;
  const w = (vb && vb.width ? vb.width : svg.clientWidth) || 800;
  const h = (vb && vb.height ? vb.height : svg.clientHeight) || 400;
  const img = new Image();
  const url = URL.createObjectURL(new Blob([text], { type: 'image/svg+xml' }));
  await new Promise<void>((resolve, reject) => { img.onload = () => resolve(); img.onerror = () => reject(new Error('Could not render the SVG')); img.src = url; });
  const canvas = document.createElement('canvas');
  canvas.width = Math.round(w * scale); canvas.height = Math.round(h * scale);
  const ctx = canvas.getContext('2d');
  if (!ctx) throw new Error('No canvas context');
  ctx.drawImage(img, 0, 0, canvas.width, canvas.height);
  URL.revokeObjectURL(url);
  const blob = await new Promise<Blob | null>((resolve) => canvas.toBlob(resolve, 'image/png'));
  if (blob) downloadBlob(filename, blob);
}
