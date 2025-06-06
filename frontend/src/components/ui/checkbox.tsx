import * as React from "react";

export const Checkbox = React.forwardRef<HTMLInputElement, React.InputHTMLAttributes<HTMLInputElement>>(
  ({ className, ...props }, ref) => (
    <input type="checkbox" ref={ref} className={className} {...props} />
  )
);
Checkbox.displayName = "Checkbox";
