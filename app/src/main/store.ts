import { app, safeStorage } from "electron";
import { existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import path from "node:path";
import { SECRET_KEYS, type SecretKey, type SecretStatus, type Settings } from "../shared/types";
import { defaultProjectsDir, isDev } from "./paths";

const userFile = (name: string) => path.join(app.getPath("userData"), name);

// --- settings (plain JSON: nothing secret in here) ---------------------------------------------

const DEFAULTS: Settings = {
  agent: "claude",
  claudeModel: "claude-sonnet-5-5",
  codexModel: "",
  codexAuth: "account",
  codexSandbox: "danger-full-access",
  projectsDir: "",
  autoApprove: false,
  hfMaxUsd: 2,
  resolveMcp: false,
  onboarded: false,
};

let settings: Settings | null = null;

export function getSettings(): Settings {
  if (!settings) {
    let saved: Partial<Settings> = {};
    try {
      saved = JSON.parse(readFileSync(userFile("settings.json"), "utf8"));
    } catch {
      /* first launch */
    }
    settings = { ...DEFAULTS, ...saved };
    // in dev the engine is the repo, whose ea CLI only knows <repo>/projects
    if (!settings.projectsDir || isDev) settings.projectsDir = defaultProjectsDir();
  }
  return settings;
}

export function setSettings(patch: Partial<Settings>): Settings {
  settings = { ...getSettings(), ...patch };
  if (isDev) settings.projectsDir = defaultProjectsDir();
  mkdirSync(app.getPath("userData"), { recursive: true });
  writeFileSync(userFile("settings.json"), JSON.stringify(settings, null, 2));
  return settings;
}

// --- secrets: encrypted with the OS keychain (safeStorage), never sent to the renderer ----------

type Secrets = Partial<Record<SecretKey, string>>;
let secrets: Secrets | null = null;

function load(): Secrets {
  if (secrets) return secrets;
  secrets = {};
  const f = userFile("secrets.bin");
  if (existsSync(f) && safeStorage.isEncryptionAvailable()) {
    try {
      secrets = JSON.parse(safeStorage.decryptString(readFileSync(f)));
    } catch {
      secrets = {}; // keychain entry changed (e.g. app re-signed): the user re-enters keys
    }
  }
  return secrets!;
}

function save(): void {
  if (!safeStorage.isEncryptionAvailable()) throw new Error("O cofre do sistema (Keychain) não está disponível.");
  mkdirSync(app.getPath("userData"), { recursive: true });
  writeFileSync(userFile("secrets.bin"), safeStorage.encryptString(JSON.stringify(load())), { mode: 0o600 });
}

export function secretStatus(): SecretStatus[] {
  const s = load();
  return SECRET_KEYS.map((key) => ({ key, set: !!s[key], hint: s[key] ? `…${s[key]!.slice(-4)}` : "" }));
}

export function setSecret(key: SecretKey, value: string): void {
  if (!SECRET_KEYS.includes(key)) throw new Error(`unknown key ${key}`);
  const v = value.trim();
  if (v) load()[key] = v;
  else delete load()[key];
  save();
}

export function getSecret(key: SecretKey): string | undefined {
  return load()[key];
}

/** Service keys handed to the engine and the agents as environment variables. */
export function serviceEnv(): Record<string, string> {
  const s = load();
  const env: Record<string, string> = { EA_HF_MAX_USD: String(getSettings().hfMaxUsd) };
  for (const k of ["ELEVENLABS_API_KEY", "ELEVENLABS_VOICE_ID", "PEXELS_API_KEY", "HF_API_KEY_ID", "HF_API_KEY_SECRET", "HF_TOKEN"] as const) {
    if (s[k]) env[k] = s[k]!;
  }
  return env;
}
