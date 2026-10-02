import React from "react";
import { C } from "./palette";

/** Placeholder mark: replace with the brand's SVG (keep it a component, sized by `size`). */
export const Logo: React.FC<{ size?: number; color?: string }> = ({ size = 120, color = C.ink }) => (
  <svg width={size} height={size} viewBox="0 0 100 100">
    <rect x="8" y="8" width="84" height="84" rx="26" fill={color} />
    <path d="M30 52 l14 14 l28 -30" stroke={C.brand} strokeWidth="10" fill="none" strokeLinecap="round" strokeLinejoin="round" />
  </svg>
);
