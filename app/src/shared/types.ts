// Contract between the Electron main process and the renderer (exposed as window.ea by the preload).

export type AgentKind = "claude" | "codex";
export type CodexAuth = "account" | "apikey";
export type CodexSandbox = "danger-full-access" | "workspace-write";

export interface Settings {
  agent: AgentKind;
  claudeModel: string;
  codexModel: string; // "" = Codex default
  codexAuth: CodexAuth;
  codexSandbox: CodexSandbox;
  projectsDir: string;
  autoApprove: boolean; // Claude: approve file edits and ea commands without asking
  hfMaxUsd: number; // Higgsfield per-generation cap (EA_HF_MAX_USD)
  resolveMcp: boolean; // give the agent live DaVinci Resolve control
  onboarded: boolean;
}

export const SECRET_KEYS = [
  "ANTHROPIC_API_KEY",
  "OPENAI_API_KEY",
  "ELEVENLABS_API_KEY",
  "ELEVENLABS_VOICE_ID",
  "PEXELS_API_KEY",
  "HF_API_KEY_ID",
  "HF_API_KEY_SECRET",
  "HF_TOKEN",
] as const;
export type SecretKey = (typeof SECRET_KEYS)[number];

export interface SecretStatus {
  key: SecretKey;
  set: boolean;
  hint: string; // last 4 characters, never the value
}

export interface Validation {
  ok: boolean;
  detail: string;
}

export interface DoctorCheck {
  name: string;
  ok: boolean;
  required: boolean;
  detail: string;
}

export interface SystemStatus {
  platform: NodeJS.Platform;
  arch: string;
  appVersion: string;
  dev: boolean;
  engineDir: string;
  engineReady: boolean; // python env synced
  tools: Record<"uv" | "ffmpeg" | "node" | "brew" | "git", string | null>;
  doctor: { ready: boolean; checks: DoctorCheck[] } | null;
  codex: { loggedIn: boolean; detail: string };
  resolveInstalled: boolean;
}

export interface ProjectSettings {
  name: string;
  fps: number;
  width: number;
  height: number;
  language?: string;
  platform?: string;
}

export interface MediaItem {
  id: string;
  path: string; // project-relative
  kind: string;
  duration?: number;
  width?: number;
  height?: number;
  fps?: number;
  has_audio?: boolean;
  derived?: boolean;
}

export interface OutputFile {
  name: string;
  path: string; // project-relative
  size: number;
  mtime: number;
  kind: "video" | "audio" | "image" | "nle" | "subtitle" | "other";
}

export interface Clip {
  media: string;
  in: number;
  out: number;
  start: number;
  note?: string;
  [k: string]: unknown;
}

export interface Track {
  kind: "video" | "audio";
  name: string;
  clips: Clip[];
}

export interface Timeline {
  name: string;
  fps: number;
  width: number;
  height: number;
  tracks: Track[];
  markers?: { time: number; note: string }[];
}

export interface ProjectSummary {
  name: string;
  dir: string;
  settings: ProjectSettings;
  inputs: number;
  hasTimeline: boolean;
  length: number; // seconds of edited timeline
  updated: number;
  poster: string | null; // project-relative video to show as a thumbnail
}

export interface ProjectDetail extends ProjectSummary {
  inputFiles: OutputFile[];
  media: MediaItem[];
  timeline: Timeline | null;
  outputs: OutputFile[];
}

export interface NewProject {
  name: string;
  preset: "youtube" | "shorts" | "square" | "podcast";
  language: string;
}

export interface Question {
  question: string;
  header: string;
  multiSelect: boolean;
  options: { label: string; description: string }[];
}

export type ChatItem =
  | { id: string; kind: "user"; text: string; ts: number }
  | { id: string; kind: "assistant"; text: string; ts: number; streaming?: boolean }
  | { id: string; kind: "thinking"; text: string; ts: number }
  | {
      id: string;
      kind: "tool";
      ts: number;
      name: string;
      title: string;
      detail: string;
      status: "running" | "done" | "error";
      output?: string;
      media?: string; // project-relative image the agent looked at (contact sheet, frame)
    }
  | {
      id: string;
      kind: "approval";
      ts: number;
      requestId: string;
      tool: string;
      title: string;
      detail: string;
      canRemember: boolean;
      status: "pending" | "allowed" | "always" | "denied";
    }
  | {
      id: string;
      kind: "question";
      ts: number;
      requestId: string;
      questions: Question[];
      status: "pending" | "answered";
      answers?: Record<string, string>;
    }
  | {
      id: string;
      kind: "result";
      ts: number;
      agent: AgentKind;
      costUsd?: number;
      tokens?: number;
      durationMs?: number;
      isError?: boolean;
      text?: string;
    }
  | { id: string; kind: "error"; text: string; ts: number }
  | { id: string; kind: "notice"; text: string; ts: number };

export type AgentState = "idle" | "running";

export type ApprovalReply = { kind: "approval"; decision: "allow" | "always" | "deny"; message?: string };
export type QuestionReply = { kind: "question"; answers: Record<string, string> };

export interface ChatHistory {
  agent: AgentKind;
  items: ChatItem[];
  state: AgentState;
}

export interface RunResult {
  ok: boolean;
  code: number | null;
  json: unknown;
  stdout: string;
  stderr: string;
}

export interface LogLine {
  channel: string; // "setup", "render:<project>", ...
  text: string;
  done?: boolean;
  ok?: boolean;
}

export interface EaApi {
  settings: {
    get(): Promise<Settings>;
    set(patch: Partial<Settings>): Promise<Settings>;
  };
  secrets: {
    status(): Promise<SecretStatus[]>;
    set(key: SecretKey, value: string): Promise<SecretStatus[]>;
    clear(key: SecretKey): Promise<SecretStatus[]>;
    validate(key: SecretKey): Promise<Validation>;
  };
  system: {
    status(refreshDoctor?: boolean): Promise<SystemStatus>;
    installTools(): Promise<boolean>;
    setupEngine(): Promise<boolean>;
    downloadWhisper(): Promise<boolean>;
    resolveMcpSetup(): Promise<boolean>;
    codexLogin(): Promise<boolean>;
    codexLogout(): Promise<boolean>;
    openExternal(url: string): Promise<void>;
    reveal(path: string): Promise<void>;
    openPath(path: string): Promise<string>;
    pickFolder(): Promise<string | null>;
    pickMedia(): Promise<string[]>;
    memoryDir(): Promise<string | null>;
    setupDone(): Promise<RunResult>;
  };
  projects: {
    list(): Promise<ProjectSummary[]>;
    create(p: NewProject): Promise<ProjectSummary>;
    get(name: string): Promise<ProjectDetail>;
    importMedia(name: string, paths: string[]): Promise<ProjectDetail>;
    trash(name: string): Promise<void>;
    run(name: string, args: string[]): Promise<RunResult>;
    mediaUrl(name: string, rel: string): string;
  };
  agent: {
    history(project: string): Promise<ChatHistory>;
    send(project: string, text: string): Promise<void>;
    stop(project: string): Promise<void>;
    reply(requestId: string, reply: ApprovalReply | QuestionReply): Promise<void>;
    reset(project: string): Promise<void>;
  };
  on: {
    chat(cb: (e: { project: string; item: ChatItem }) => void): () => void;
    state(cb: (e: { project: string; state: AgentState }) => void): () => void;
    log(cb: (l: LogLine) => void): () => void;
    projectChanged(cb: (name: string) => void): () => void;
  };
  pathForFile(file: File): string;
}
