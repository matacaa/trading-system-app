"use client";

import { useCallback, useEffect, useRef, useState } from "react";

export function useNotifications() {
  const [permission, setPermission] = useState<NotificationPermission>("default");

  useEffect(() => {
    if (typeof window !== "undefined" && "Notification" in window) {
      setPermission(Notification.permission);
    }
  }, []);

  const requestPermission = useCallback(async () => {
    if (!("Notification" in window)) return "denied" as const;
    const result = await Notification.requestPermission();
    setPermission(result);
    return result;
  }, []);

  const sendNotification = useCallback(
    (title: string, options?: NotificationOptions) => {
      if (permission !== "granted") return;
      if (document.visibilityState === "visible") return; // Don't notify if tab is active

      try {
        new Notification(title, {
          icon: "/favicon.ico",
          badge: "/favicon.ico",
          ...options,
        });
      } catch {
        // Safari/iOS doesn't support Notification constructor
      }
    },
    [permission]
  );

  return { permission, requestPermission, sendNotification };
}

// ── Tab badge (document title) ─────────────────────────────────────────────

const BASE_TITLE = "Squawks ML";

export function useTabBadge(count: number) {
  useEffect(() => {
    if (count > 0) {
      document.title = `(${count}) ${BASE_TITLE}`;
    } else {
      document.title = BASE_TITLE;
    }
    return () => {
      document.title = BASE_TITLE;
    };
  }, [count]);
}
