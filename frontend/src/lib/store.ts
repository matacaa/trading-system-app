import { create } from "zustand";
import api, { setTokens, clearTokens, getAccessToken } from "./api";

// ── Types ──────────────────────────────────────────────────────────────────

export interface User {
  id: string;
  email: string;
  display_name: string | null;
  plan: string;
  trial_end: string | null;
  is_active: boolean;
  created_at: string;
  last_login_at: string | null;
}

export interface Preferences {
  tickers: string[];
  notification_prefs: Record<string, unknown> | null;
  theme: string | null;
  language: string | null;
  onboarding_completed: boolean;
  risk_profile: string | null;
  default_capital: number | null;
  default_timeframe: string | null;
  max_tickers: number | null;
}

interface AuthState {
  user: User | null;
  preferences: Preferences | null;
  isLoading: boolean;
  isAuthenticated: boolean;

  login: (email: string, password: string) => Promise<void>;
  register: (email: string, password: string, displayName?: string) => Promise<void>;
  logout: () => void;
  fetchMe: () => Promise<void>;
  hydrate: () => Promise<void>;
}

// ── Store ──────────────────────────────────────────────────────────────────

export const useAuthStore = create<AuthState>((set) => ({
  user: null,
  preferences: null,
  isLoading: true,
  isAuthenticated: false,

  login: async (email, password) => {
    const { data } = await api.post("/auth/login", { email, password });
    setTokens(data.access_token, data.refresh_token);
    // Fetch full user profile
    const me = await api.get("/auth/me");
    set({
      user: me.data.user,
      preferences: me.data.preferences,
      isAuthenticated: true,
    });
  },

  register: async (email, password, displayName) => {
    const { data } = await api.post("/auth/register", {
      email,
      password,
      display_name: displayName || undefined,
    });
    setTokens(data.access_token, data.refresh_token);
    const me = await api.get("/auth/me");
    set({
      user: me.data.user,
      preferences: me.data.preferences,
      isAuthenticated: true,
    });
  },

  logout: () => {
    clearTokens();
    set({ user: null, preferences: null, isAuthenticated: false });
    window.location.href = "/login";
  },

  fetchMe: async () => {
    try {
      const { data } = await api.get("/auth/me");
      set({
        user: data.user,
        preferences: data.preferences,
        isAuthenticated: true,
      });
    } catch {
      set({ user: null, preferences: null, isAuthenticated: false });
    }
  },

  hydrate: async () => {
    const token = getAccessToken();
    if (!token) {
      set({ isLoading: false, isAuthenticated: false });
      return;
    }
    try {
      const { data } = await api.get("/auth/me");
      set({
        user: data.user,
        preferences: data.preferences,
        isAuthenticated: true,
        isLoading: false,
      });
    } catch {
      clearTokens();
      set({
        user: null,
        preferences: null,
        isAuthenticated: false,
        isLoading: false,
      });
    }
  },
}));
