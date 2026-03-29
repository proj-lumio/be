import * as React from "react"
import { useEffect, useCallback } from "react"
import { X } from "lucide-react"
import { cn } from "./utils"

interface ModalProps {
  open: boolean
  onClose: () => void
  children: React.ReactNode
  className?: string
  /** Close on backdrop click (default: true) */
  dismissible?: boolean
}

function Modal({ open, onClose, children, className, dismissible = true }: ModalProps) {
  const handleKeyDown = useCallback(
    (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose()
    },
    [onClose]
  )

  useEffect(() => {
    if (open) {
      document.addEventListener("keydown", handleKeyDown)
      document.body.style.overflow = "hidden"
    }
    return () => {
      document.removeEventListener("keydown", handleKeyDown)
      document.body.style.overflow = ""
    }
  }, [open, handleKeyDown])

  if (!open) return null

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center"
      style={{ backdropFilter: "blur(8px)", background: "rgba(0,0,0,0.6)" }}
      onClick={dismissible ? onClose : undefined}
    >
      <div
        className={cn("liquid-card relative w-full max-w-lg p-6", className)}
        onClick={(e) => e.stopPropagation()}
        style={{
          animation: "modal-in 200ms ease-out",
        }}
      >
        <button
          onClick={onClose}
          className="absolute right-4 top-4 flex h-8 w-8 items-center justify-center text-white/50 transition-colors hover:text-white"
          style={{ borderRadius: 12 }}
        >
          <X className="h-4 w-4" />
        </button>
        {children}
      </div>
    </div>
  )
}

function ModalTitle({ children, className }: { children: React.ReactNode; className?: string }) {
  return <h2 className={cn("mb-4 text-lg font-semibold text-white", className)}>{children}</h2>
}

function ModalBody({ children, className }: { children: React.ReactNode; className?: string }) {
  return <div className={cn("text-sm text-muted-foreground", className)}>{children}</div>
}

function ModalFooter({ children, className }: { children: React.ReactNode; className?: string }) {
  return <div className={cn("mt-6 flex justify-end gap-3", className)}>{children}</div>
}

export { Modal, ModalTitle, ModalBody, ModalFooter }
