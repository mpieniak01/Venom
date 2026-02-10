import * as React from "react"
import { cn } from "@/lib/utils"

type LabelProps = Omit<React.LabelHTMLAttributes<HTMLLabelElement>, "htmlFor"> & {
    htmlFor: string
}

const Label = React.forwardRef<
    HTMLLabelElement,
    LabelProps
>(({ className, htmlFor, ...props }, ref) => (
    <label
        ref={ref}
        htmlFor={htmlFor}
        className={cn(
            "text-sm font-medium leading-none peer-disabled:cursor-not-allowed peer-disabled:opacity-70",
            className
        )}
        {...props}
    />
))
Label.displayName = "Label"
export { Label }
