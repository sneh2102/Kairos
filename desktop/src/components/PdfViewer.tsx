// Chromium (Electron) has a built-in PDF viewer — no pdf.js needed.
export default function PdfViewer({ url, title }: { url: string; title: string }) {
  return (
    <embed
      src={url}
      type="application/pdf"
      title={title}
      className="w-full h-full rounded-md border border-border bg-white"
    />
  );
}
