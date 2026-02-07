import type { SVGProps } from "react";

export type InkIconName =
  | "menu"
  | "home"
  | "notes"
  | "todos"
  | "calendar"
  | "search"
  | "notifications"
  | "settings"
  | "theme"
  | "palette"
  | "logout";

type InkIconProps = {
  name: InkIconName;
  size?: number;
  title?: string;
} & Omit<SVGProps<SVGSVGElement>, "children">;

export function InkIcon({ name, size = 20, title, ...props }: InkIconProps) {
  const common: SVGProps<SVGSVGElement> = {
    width: size,
    height: size,
    viewBox: "0 0 24 24",
    fill: "none",
    stroke: "currentColor",
    strokeWidth: 1.8,
    strokeLinecap: "round",
    strokeLinejoin: "round",
    "aria-hidden": title ? undefined : true,
    ...props,
  };

  const titleEl = title ? <title>{title}</title> : null;

  switch (name) {
    case "menu":
      return (
        <svg {...common} role={title ? "img" : undefined}>
          {titleEl}
          <path d="M4 7h16" />
          <path d="M4 12h16" />
          <path d="M4 17h16" />
        </svg>
      );
    case "home":
      return (
        <svg {...common} role={title ? "img" : undefined}>
          {titleEl}
          <path d="M4 11.5 12 5l8 6.5" />
          <path d="M6.5 10.8V19h11V10.8" />
        </svg>
      );
    case "notes":
      return (
        <svg {...common} role={title ? "img" : undefined}>
          {titleEl}
          <path d="M7 4h7l3 3v13a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2Z" />
          <path d="M14 4v4h4" />
          <path d="M8 12h8" />
          <path d="M8 15.5h8" />
        </svg>
      );
    case "todos":
      return (
        <svg {...common} role={title ? "img" : undefined}>
          {titleEl}
          <path d="M6 4h12a2 2 0 0 1 2 2v12a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2Z" />
          <path d="m8 12 2.2 2.2L16 8.5" />
        </svg>
      );
    case "calendar":
      return (
        <svg {...common} role={title ? "img" : undefined}>
          {titleEl}
          <path d="M7 4v3" />
          <path d="M17 4v3" />
          <path d="M5 9h14" />
          <path d="M6.5 6h11A2.5 2.5 0 0 1 20 8.5v10A2.5 2.5 0 0 1 17.5 21h-11A2.5 2.5 0 0 1 4 18.5v-10A2.5 2.5 0 0 1 6.5 6Z" />
        </svg>
      );
    case "search":
      return (
        <svg {...common} role={title ? "img" : undefined}>
          {titleEl}
          <path d="M10.5 18a7.5 7.5 0 1 1 0-15 7.5 7.5 0 0 1 0 15Z" />
          <path d="M16.2 16.2 21 21" />
        </svg>
      );
    case "notifications":
      return (
        <svg {...common} role={title ? "img" : undefined}>
          {titleEl}
          <path d="M18 8a6 6 0 1 0-12 0c0 7-3 7-3 7h18s-3 0-3-7" />
          <path d="M10 19a2 2 0 0 0 4 0" />
        </svg>
      );
    case "settings":
      return (
        <svg {...common} role={title ? "img" : undefined}>
          {titleEl}
          <path d="M12 15.4a3.4 3.4 0 1 0 0-6.8 3.4 3.4 0 0 0 0 6.8Z" />
          <path d="M19.4 15a8.6 8.6 0 0 0 .1-2l2-1.2-2-3.4-2.3.6a8.7 8.7 0 0 0-1.7-1L15.1 5H8.9L8.5 8a8.7 8.7 0 0 0-1.7 1l-2.3-.6-2 3.4 2 1.2a8.6 8.6 0 0 0 .1 2l-2 1.2 2 3.4 2.3-.6a8.7 8.7 0 0 0 1.7 1l.4 3h6.2l.4-3a8.7 8.7 0 0 0 1.7-1l2.3.6 2-3.4-2-1.2Z" />
        </svg>
      );
    case "theme":
      return (
        <svg {...common} role={title ? "img" : undefined}>
          {titleEl}
          <path d="M12 3a7 7 0 1 0 9 9 8.5 8.5 0 0 1-9-9Z" />
        </svg>
      );
    case "palette":
      return (
        <svg {...common} role={title ? "img" : undefined}>
          {titleEl}
          <path d="M12 3a9 9 0 0 0 0 18h1.2a2.3 2.3 0 0 0 0-4.6H12a2.3 2.3 0 0 1 0-4.6h4a4.6 4.6 0 0 0 0-9.2H12Z" />
          <path d="M8 9.2h.01" />
          <path d="M10.7 6.8h.01" />
          <path d="M14 6.8h.01" />
          <path d="M16.6 9.2h.01" />
        </svg>
      );
    case "logout":
      return (
        <svg {...common} role={title ? "img" : undefined}>
          {titleEl}
          <path d="M10 7V6a2 2 0 0 1 2-2h7v16h-7a2 2 0 0 1-2-2v-1" />
          <path d="M4 12h10" />
          <path d="m7 9-3 3 3 3" />
        </svg>
      );
    default:
      return (
        <svg {...common} role={title ? "img" : undefined}>
          {titleEl}
          <path d="M12 12h.01" />
        </svg>
      );
  }
}

