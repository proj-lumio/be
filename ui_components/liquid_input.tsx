import { forwardRef, useState } from "react"
import { Eye, EyeOff } from "lucide-react"
import { cn } from "./utils"

interface LiquidInputProps extends React.InputHTMLAttributes<HTMLInputElement> {
  wrapperClassName?: string
}

const LiquidInput = forwardRef<HTMLInputElement, LiquidInputProps>(
  ({ wrapperClassName, className, type, ...props }, ref) => {
    const isPassword = type === "password"
    const [visible, setVisible] = useState(false)

    return (
      <div className={cn("liquid-input", wrapperClassName)}>
        <input
          ref={ref}
          type={isPassword && visible ? "text" : type}
          className={cn(
            "h-full w-full bg-transparent px-4 text-sm text-white placeholder:text-[#555] focus:outline-none",
            isPassword && "pr-11",
            className
          )}
          {...props}
        />
        {isPassword && (
          <button
            type="button"
            tabIndex={-1}
            onClick={() => setVisible((v) => !v)}
            className="absolute right-3 top-1/2 z-10 flex h-8 w-8 -translate-y-1/2 items-center justify-center text-white transition-all duration-200 hover:text-white/80"
          >
            <div
              className="transition-all duration-200"
              style={{
                transform: visible ? "scale(1) rotate(0deg)" : "scale(0.85) rotate(-15deg)",
                opacity: visible ? 1 : 0.7,
              }}
            >
              {visible ? <Eye className="h-5 w-5" /> : <EyeOff className="h-5 w-5" />}
            </div>
          </button>
        )}
      </div>
    )
  }
)
LiquidInput.displayName = "LiquidInput"

export { LiquidInput }
export type { LiquidInputProps }
