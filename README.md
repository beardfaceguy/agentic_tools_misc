# agentic_tools_misc

A collection of small, single-purpose utilities for working with AI coding
agents and the tools that host them (Cursor, etc.). Each tool lives in its
own directory with a self-contained README.

## Layout

```
agentic_tools_misc/
├── README.md                       # this file
├── behavior-template/              # unified global AI rules across IDEs
│   ├── README.md
│   ├── CUSTOMIZING.md
│   ├── install.sh
│   ├── global-behavior.md
│   ├── sync-rules.sh
│   └── systemd/
│       ├── ai-rules-sync.path
│       └── ai-rules-sync.service
└── migrate-cursor-chat/            # re-bind Cursor chats to a moved workspace
    ├── README.md
    └── migrate-cursor-chat.py
```

## Tools

| Directory | What it does |
|-----------|--------------|
| [`behavior-template/`](./behavior-template/) | Write AI agent behavioral rules once, auto-sync to Claude Code, Zed, and Cursor IDE. Uses a systemd file watcher to propagate edits from a single canonical file. |
| [`migrate-cursor-chat/`](./migrate-cursor-chat/) | Re-associate Cursor chat history with a new workspace path after moving the workspace folder on disk. Rewrites the embedded `workspaceIdentifier` in `state.vscdb` and copies per-chat agent transcripts. |

## Conventions

- Each tool gets its own directory.
- Each directory contains a `README.md` covering: the problem, requirements,
  usage, how it works internally, and recovery/caveats.
- Prefer the standard library; flag any external dependencies prominently.
- Destructive tools must support `--dry-run` and create a timestamped backup
  before writing.
