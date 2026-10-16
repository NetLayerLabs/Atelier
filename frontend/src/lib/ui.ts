"use client";

// Header-level UI state shared between the header controls and the Menu sheet (which can open the same panels).

import { create } from "zustand";

interface UiState {
  inferenceOpen: boolean;
  healthOpen: boolean;
  menuOpen: boolean;
  setInferenceOpen: (open: boolean) => void;
  setHealthOpen: (open: boolean) => void;
  setMenuOpen: (open: boolean) => void;
}

export const useUi = create<UiState>((set) => ({
  inferenceOpen: false,
  healthOpen: false,
  menuOpen: false,
  setInferenceOpen: (inferenceOpen) => set({ inferenceOpen }),
  setHealthOpen: (healthOpen) => set({ healthOpen }),
  setMenuOpen: (menuOpen) => set({ menuOpen }),
}));
