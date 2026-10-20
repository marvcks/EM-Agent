import React from "react";
import { cn } from "#/utils/utils";

export type TextShimmerProps = {
  children: string;
  as?: React.ElementType;
  className?: string;
  active?: boolean;
  duration?: number;
  spread?: number;
} & Omit<React.HTMLAttributes<HTMLElement>, "children" | "className">;

// @spec TSH-001 — Active state only changes text paint, preserving the element
function TextShimmerComponent({
  children,
  as: Component = "p",
  className,
  active = true,
  duration = 2.8,
  spread = 2,
  style,
  ...rest
}: TextShimmerProps) {
  return (
    <Component
      {...rest}
      className={cn("oh-text-shimmer inline-block", className)}
      data-shimmer-active={active}
      style={
        {
          "--oh-shimmer-duration": duration,
          "--oh-shimmer-spread": spread,
          ...style,
        } as React.CSSProperties
      }
    >
      {children}
    </Component>
  );
}

export const TextShimmer = React.memo(TextShimmerComponent);
