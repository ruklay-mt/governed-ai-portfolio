"use client";

import { useEffect } from "react";

import { apiBaseUrl } from "@/lib/env";

/** Fire one health check so Cloud Run and Neon start waking while the visitor reads. */
export function WarmUp() {
  useEffect(() => {
    fetch(`${apiBaseUrl()}/api/health`, { cache: "no-store" }).catch(() => {});
  }, []);
  return null;
}
