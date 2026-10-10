import type { SVGProps } from "react";

type IconProps = SVGProps<SVGSVGElement> & { size?: number };

function Svg({ size = 20, children, ...rest }: IconProps & { children: React.ReactNode }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.4}
         strokeLinecap="square" aria-hidden="true" {...rest}>
      {children}
    </svg>
  );
}

export const IconHome = (p: IconProps) => (
  <Svg {...p}><circle cx="12" cy="12" r="8" /><circle cx="12" cy="12" r="3" /><path d="M12 2v3M12 19v3M2 12h3M19 12h3" /></Svg>
);
export const IconApps = (p: IconProps) => (
  <Svg {...p}><rect x="3" y="3" width="7" height="7" /><rect x="14" y="3" width="7" height="7" /><rect x="3" y="14" width="7" height="7" /><path d="M14 17.5h7M17.5 14v7" /></Svg>
);
export const IconScenario = (p: IconProps) => (
  <Svg {...p}><path d="M4 6h10M4 12h16M4 18h7" /><path d="M17 4l3 2-3 2" /><path d="M14 16l3 2-3 2" /></Svg>
);
export const IconLog = (p: IconProps) => (
  <Svg {...p}><rect x="4" y="3" width="16" height="18" /><path d="M8 8h8M8 12h8M8 16h5" /></Svg>
);
export const IconShield = (p: IconProps) => (
  <Svg {...p}><path d="M12 3l8 3v6c0 4.5-3.4 8-8 9-4.6-1-8-4.5-8-9V6z" /><path d="M9 12l2 2 4-4" /></Svg>
);
export const IconSettings = (p: IconProps) => (
  <Svg {...p}><path d="M4 7h10M18 7h2M4 17h4M12 17h8" /><rect x="14" y="5" width="4" height="4" /><rect x="8" y="15" width="4" height="4" /></Svg>
);
export const IconDiag = (p: IconProps) => (
  <Svg {...p}><path d="M3 12h4l2-5 4 10 2-5h6" /></Svg>
);
export const IconMic = (p: IconProps) => (
  <Svg {...p}><rect x="9" y="3" width="6" height="11" rx="3" /><path d="M5 11a7 7 0 0014 0M12 18v3" /></Svg>
);
export const IconCam = (p: IconProps) => (
  <Svg {...p}><rect x="3" y="7" width="13" height="10" /><path d="M16 10l5-3v10l-5-3" /></Svg>
);
export const IconNet = (p: IconProps) => (
  <Svg {...p}><circle cx="12" cy="12" r="9" /><path d="M3 12h18M12 3c3 3 3 15 0 18M12 3c-3 3-3 15 0 18" /></Svg>
);
export const IconChip = (p: IconProps) => (
  <Svg {...p}><rect x="6" y="6" width="12" height="12" /><path d="M9 2v4M15 2v4M9 18v4M15 18v4M2 9h4M2 15h4M18 9h4M18 15h4" /></Svg>
);
export const IconStop = (p: IconProps) => (
  <Svg {...p}><path d="M8 3h8l5 5v8l-5 5H8l-5-5V8z" /><path d="M8 12h8" /></Svg>
);
export const IconUndo = (p: IconProps) => (
  <Svg {...p}><path d="M9 7L4 12l5 5" /><path d="M4 12h11a5 5 0 010 10h-3" /></Svg>
);
export const IconRepeat = (p: IconProps) => (
  <Svg {...p}><path d="M4 12a8 8 0 0114-5l2 2" /><path d="M20 4v5h-5" /><path d="M20 12a8 8 0 01-14 5l-2-2" /><path d="M4 20v-5h5" /></Svg>
);
export const IconPlay = (p: IconProps) => (
  <Svg {...p}><path d="M7 4l13 8-13 8z" /></Svg>
);
export const IconPlus = (p: IconProps) => (
  <Svg {...p}><path d="M12 4v16M4 12h16" /></Svg>
);
export const IconSearch = (p: IconProps) => (
  <Svg {...p}><circle cx="10.5" cy="10.5" r="6.5" /><path d="M15.5 15.5L21 21" /></Svg>
);
export const IconTrash = (p: IconProps) => (
  <Svg {...p}><path d="M4 7h16M9 7V4h6v3M6 7l1 14h10l1-14" /></Svg>
);
export const IconEdit = (p: IconProps) => (
  <Svg {...p}><path d="M4 20h4L20 8l-4-4L4 16z" /></Svg>
);
export const IconPin = (p: IconProps) => (
  <Svg {...p}><path d="M9 3h6l-1 6 4 4H6l4-4z" /><path d="M12 13v8" /></Svg>
);
export const IconCompact = (p: IconProps) => (
  <Svg {...p}><rect x="3" y="3" width="18" height="18" /><rect x="12" y="13" width="7" height="6" /></Svg>
);
export const IconMinimize = (p: IconProps) => (
  <Svg {...p}><path d="M6 12h12" /></Svg>
);
export const IconMaximize = (p: IconProps) => (
  <Svg {...p}><rect x="6" y="6" width="12" height="12" /></Svg>
);
export const IconClose = (p: IconProps) => (
  <Svg {...p}><path d="M6 6l12 12M18 6L6 18" /></Svg>
);
export const IconExpand = (p: IconProps) => (
  <Svg {...p}><path d="M4 10V4h6M20 14v6h-6M4 4l7 7M20 20l-7-7" /></Svg>
);
export const IconFolder = (p: IconProps) => (
  <Svg {...p}><path d="M3 6h7l2 2h9v11H3z" /></Svg>
);
export const IconSend = (p: IconProps) => (
  <Svg {...p}><path d="M4 12h14M13 6l6 6-6 6" /></Svg>
);
