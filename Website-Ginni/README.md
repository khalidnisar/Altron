# Website-Ginni

Website-Ginni is a Claude Code skill package for owner-authorized website migrations and clean-room reconstructions.

It can help:

- Rebuild an authorized frontend with measured visual, responsive, semantic, and behavioral parity.
- Migrate an actual backend when the owner provides source, data exports, configuration, and infrastructure access.
- Build a new clean-room backend from approved API contracts, business rules, and synthetic fixtures.
- Produce route, state, journey, endpoint, asset, architecture, parity, testing, and handoff artifacts.

A URL alone cannot expose hidden server source, databases, credentials, jobs, or infrastructure. Website-Ginni does not provide phishing, credential collection, access-control bypass, impersonation, or intellectual-property theft workflows.

## Use with Claude Code

From this repository:

```bash
cd Website-Ginni
claude
```

Then invoke:

```text
/authorized-site-rebuilder https://your-authorized-site.example ./replacement
```

Claude Code discovers the project skill at:

```text
Website-Ginni/.claude/skills/authorized-site-rebuilder/SKILL.md
```

See the [skill README](.claude/skills/authorized-site-rebuilder/README.md) for installation, workspace initialization, validation, testing, and the complete file layout.

## Package layout

```text
Website-Ginni/
├── README.md
├── .gitignore
└── .claude/
    └── skills/
        └── authorized-site-rebuilder/
            ├── SKILL.md
            ├── README.md
            ├── assets/
            ├── evals/
            ├── references/
            └── scripts/
```
