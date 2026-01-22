# Documentation Index

Overview of all documentation files in the Literature Review Assistant project.

## Quick Navigation

### User-Facing Documentation

- **[README.md](../README.md)** - Quick start guide, prerequisites, workflow overview, basic usage
- **[Architecture](ARCHITECTURE.md)** - Architecture overview, design patterns, phase registry pattern, module dependencies
- **[Configuration Reference](CONFIGURATION.md)** - Complete configuration options and settings for `config/workflow.yaml`
- **[Examples](EXAMPLES.md)** - Code examples and use cases for common scenarios
- **[Advanced Features](ADVANCED_FEATURES.md)** - Detailed documentation for advanced features:
  - Bibliometric features (Google Scholar, Scopus, Author Service)
  - Git integration for manuscripts
  - Quality assessment workflow
  - Manuscript pipeline (Manubot, submission packages)
  - Citation resolution and CSL styles
  - Journal templates
  - Text humanization
  - Visualization tools (Mermaid diagrams, tables)
- **[Troubleshooting Guide](TROUBLESHOOTING.md)** - Detailed troubleshooting for common issues and solutions

### Developer Documentation

- **[Development Guide](../DEVELOPMENT.md)** - Developer-focused documentation:
  - Development setup and environment
  - Code style and linting (ruff)
  - Testing strategy and organization
  - Bibliometric features testing
  - Development workflow
  - Contributing guidelines
  - Debugging
  - Release process

### Test Documentation

- **[Test Organization Guide](../tests/README.md)** - Test structure, naming conventions, running tests, test discovery tools

## Documentation Structure

```
.
├── README.md                    # User-facing quick start (445 lines)
├── DEVELOPMENT.md               # Developer guide (576 lines)
├── docs/
│   ├── README.md                # This file - documentation index
│   ├── ARCHITECTURE.md          # Architecture and design patterns
│   ├── CONFIGURATION.md         # Complete configuration reference
│   ├── EXAMPLES.md              # Code examples and use cases
│   ├── ADVANCED_FEATURES.md     # Advanced features documentation (818 lines)
│   └── TROUBLESHOOTING.md       # Troubleshooting guide
└── tests/
    └── README.md                # Test organization guide (381 lines)
```

## Getting Started

### For Users

1. Start with **[README.md](../README.md)** for quick start and basic usage
2. Review **[Configuration Reference](CONFIGURATION.md)** to customize your workflow
3. Check **[Examples](EXAMPLES.md)** for common use cases
4. See **[Advanced Features](ADVANCED_FEATURES.md)** for advanced functionality
5. Refer to **[Troubleshooting Guide](TROUBLESHOOTING.md)** if you encounter issues

### For Developers

1. Read **[README.md](../README.md)** to understand the project
2. Follow **[Development Guide](../DEVELOPMENT.md)** for setup and workflow
3. Review **[Architecture](ARCHITECTURE.md)** to understand the system design
4. Check **[Test Organization Guide](../tests/README.md)** for testing guidelines

## Documentation Best Practices

- **README.md**: Keep concise (~400-500 lines), focus on quick start and essentials
- **docs/**: Detailed user-facing documentation
- **DEVELOPMENT.md**: Developer-focused content (setup, testing, contributing)
- **tests/README.md**: Test-specific documentation

## Contributing to Documentation

When adding or updating documentation:

1. **User-facing changes**: Update relevant files in `docs/` or `README.md`
2. **Developer changes**: Update `DEVELOPMENT.md` or `tests/README.md`
3. **New features**: Add to appropriate documentation file or create new section
4. **Keep it concise**: Follow markdown best practices (max 3-4 heading levels, 80-100 char line length)
5. **Update this index**: If adding new documentation files, update this README.md

## File Sizes

Current documentation file sizes (as of consolidation):
- README.md: 445 lines
- DEVELOPMENT.md: 576 lines
- docs/ADVANCED_FEATURES.md: 818 lines
- docs/CONFIGURATION.md: ~300 lines
- docs/EXAMPLES.md: ~200 lines
- docs/ARCHITECTURE.md: ~150 lines
- docs/TROUBLESHOOTING.md: ~110 lines
- tests/README.md: 381 lines

Total: ~3,000 lines of documentation
