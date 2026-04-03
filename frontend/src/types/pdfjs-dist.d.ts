declare module 'pdfjs-dist/build/pdf.mjs' {
  export const GlobalWorkerOptions: {
    workerSrc: string
  }

  export interface PDFPageViewport {
    width: number
    height: number
  }

  export interface PDFPageProxy {
    getViewport(params: { scale: number }): PDFPageViewport
    render(params: { canvasContext: CanvasRenderingContext2D; viewport: PDFPageViewport }): { promise: Promise<void> }
    cleanup(): void
  }

  export interface PDFDocumentProxy {
    numPages: number
    getPage(pageNumber: number): Promise<PDFPageProxy>
  }

  export function getDocument(params: { data: ArrayBuffer | Uint8Array }): {
    promise: Promise<PDFDocumentProxy>
  }
}
