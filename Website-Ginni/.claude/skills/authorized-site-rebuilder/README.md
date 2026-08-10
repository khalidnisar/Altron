# Authorized Site Rebuilder — Claude Code Skill

A project-level Claude Code skill for planning and executing a high-fidelity, owner-authorized website migration or clean-room reconstruction.

## What it can do

- Rebuild an authorized, browser-observable frontend with measured visual, responsive, semantic, and behavioral parity.
- Migrate an actual backend when the owner provides source, data/object exports, configuration inventory, and infrastructure access.
- Create a new clean-room backend from owner requirements, API schemas, sanitized network contracts, and synthetic fixtures.
- Produce route/state/journey/endpoint/asset inventories, architecture, OpenAPI starter, parity matrix, test plan, and handoff.
- Keep authorization, privacy, secrets, asset rights, accessibility, security, backup/restore, and rollback explicit.

## What it cannot do

A URL does not expose hidden server source, databases, secret keys, private configuration, jobs, or infrastructure. The skill never claims to “download” a backend and does not provide bypass, phishing, credential-collection, impersonation, or IP-theft workflows.

Without reproduction authorization, it switches to **inspiration-only** mode: distinct branding, original content/assets, and no target crawl.

## Use in this repository

The checked-in project skill is discovered automatically from:

```text
Website-Ginni/.claude/skills/authorized-site-rebuilder/SKILL.md
```

Start Claude Code inside the Website-Ginni folder:

```bash
cd Website-Ginni
claude
```

Then invoke:

```text
/authorized-site-rebuilder https://your-authorized-site.example ./replacement
```

Or ask naturally:

```text
Rebuild the site I own at https://your-authorized-site.example in this repository.
```

The skill first asks for missing authorization/scope details. It must not browse the target before that gate passes.

## Install as a personal skill

To use it across projects, copy the entire directory—not only `SKILL.md`—to:

```bash
mkdir -p ~/.claude/skills
cp -R Website-Ginni/.claude/skills/authorized-site-rebuilder ~/.claude/skills/
```

Then invoke `/authorized-site-rebuilder` from any project. Review skill files before trusting them, as with any executable project configuration.

## Initialize the evidence workspace

After authorization is confirmed:

From the repository root:

```bash
python Website-Ginni/.claude/skills/authorized-site-rebuilder/scripts/init_workspace.py \
  --url "https://your-authorized-site.example" \
  --output .site-rebuild \
  --mode black-box-authorized \
  --authorization confirmed \
  --authorization-reference "owner-confirmed YYYY-MM-DD"
```

Modes:

- `source-assisted`
- `contract-assisted`
- `black-box-authorized`
- `inspiration-only` (requires `--authorization inspiration-only`)

The initializer makes **zero network requests**. It refuses to overwrite a nonempty directory; `--resume` only adds missing files to a matching initialized workspace.

## Validate artifacts and scan for common secrets

```bash
python Website-Ginni/.claude/skills/authorized-site-rebuilder/scripts/validate_workspace.py \
  --root .site-rebuild
```

Use `--json` for machine-readable results or `--strict` to fail on unfinished `TBD` markers. The scanner is best-effort only; manually review all evidence and run a dedicated secret scanner before commit.

## Blueprint structure

```text
authorized-site-rebuilder/
├── SKILL.md
├── README.md
├── assets/                     # Workspace templates
├── evals/evals.json            # Behavior evaluation cases
├── references/
│   ├── approach-matrix.md
│   ├── safety-and-scope.md
│   ├── discovery-and-capture.md
│   ├── frontend-rebuild.md
│   ├── backend-rebuild.md
│   ├── validation-and-delivery.md
│   └── tooling-and-sources.md
└── scripts/
    ├── init_workspace.py
    ├── validate_workspace.py
    └── test_scripts.py
```

The design follows Agent Skills progressive disclosure: the main instructions stay in `SKILL.md`; detailed phase guidance loads from `references/` only when needed.

## Suggested first test

1. Use a site you own, a local demo, or a purpose-built test application.
2. Confirm authorization and set a tiny scope: one public route, one viewport, no writes.
3. Initialize `.site-rebuild`.
4. Verify the skill produces scope/inventory artifacts before attempting implementation.
5. Confirm no secrets or raw auth state enter the repository.
6. Expand one journey at a time and compare against a no-skill baseline for trigger accuracy and output quality.

Primary format references are listed in `references/tooling-and-sources.md`.
