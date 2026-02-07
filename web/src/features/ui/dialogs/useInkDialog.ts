import { useContext } from "react";

import { InkDialogContext } from "./InkDialogProvider";

export function useInkDialog() {
  const ctx = useContext(InkDialogContext);
  if (!ctx) {
    throw new Error("useInkDialog 必须在 InkDialogProvider 内使用");
  }
  return ctx;
}

