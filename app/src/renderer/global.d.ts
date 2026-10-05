import type { EaApi } from "../shared/types";

declare global {
  interface Window {
    ea: EaApi;
  }
}
