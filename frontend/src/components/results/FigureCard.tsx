import { useState, type ReactNode } from "react"
import { Download, ImageOff, Maximize2 } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Dialog, DialogContent, DialogDescription, DialogTitle } from "@/components/ui/dialog"
import { RESULTS_DOWNLOAD_BTN_CLS } from "./resultsShared"

interface FigureCardProps {
  src: string
  downloadHref: string
  downloadName: string
  title: string
  caption?: ReactNode
  icon?: ReactNode
  showImage?: boolean
}

export function FigureCard({
  src,
  downloadHref,
  downloadName,
  title,
  caption,
  icon,
  showImage = true,
}: FigureCardProps) {
  const [imgError, setImgError] = useState(false)
  const [open, setOpen] = useState(false)
  const previewable = showImage && !imgError

  return (
    <figure className="rounded-panel border border-border bg-card overflow-hidden">
      <div className="px-3 py-2 border-b border-border bg-surface-1/60 flex items-center justify-between gap-2">
        <figcaption className="flex items-center gap-2 min-w-0 text-sm font-medium text-foreground">
          {icon}
          <span className="truncate" title={title}>
            {caption ?? title}
          </span>
        </figcaption>
        {imgError ? (
          <span className="shrink-0 text-xs text-muted border border-border rounded px-2 py-1">
            Preview unavailable
          </span>
        ) : (
          <Button size="sm" variant="outline" asChild className={`shrink-0 ${RESULTS_DOWNLOAD_BTN_CLS}`}>
            <a href={downloadHref} download={downloadName} className="gap-1.5" aria-label={`Download ${title}`}>
              <Download className="h-3.5 w-3.5" />
              Download
            </a>
          </Button>
        )}
      </div>
      {showImage && imgError && (
        <div className="aspect-[4/3] flex flex-col items-center justify-center gap-2 bg-surface-1/20 text-xs text-muted">
          <ImageOff className="h-5 w-5" aria-hidden />
          Preview unavailable
        </div>
      )}
      {previewable && (
        <>
          <button
            type="button"
            onClick={() => setOpen(true)}
            aria-label={`Open ${title} full size`}
            className="group relative block w-full aspect-[4/3] p-2 bg-surface-1/20 cursor-zoom-in focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-ring"
          >
            <img
              src={src}
              alt={title}
              className="h-full w-full rounded-lg object-contain"
              loading="lazy"
              onError={() => setImgError(true)}
            />
            <span className="absolute right-3 top-3 rounded-control bg-card/90 p-1 text-muted opacity-0 transition-opacity group-hover:opacity-100 group-focus-visible:opacity-100">
              <Maximize2 className="h-3.5 w-3.5" aria-hidden />
            </span>
          </button>
          <Dialog open={open} onOpenChange={setOpen}>
            <DialogContent className="max-w-[min(96vw,80rem)] p-4">
              <DialogTitle className="pr-8 text-sm">{title}</DialogTitle>
              <DialogDescription className="sr-only">Full-size figure preview</DialogDescription>
              <img src={src} alt={title} className="max-h-[80dvh] w-full rounded-lg object-contain" />
            </DialogContent>
          </Dialog>
        </>
      )}
    </figure>
  )
}
