#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

PLACEHOLDER_PKG="package_name"
PLACEHOLDER_PASCAL="PackageName"
PLACEHOLDER_PREFIX="PKG"

read -r -p "Package name (snake_case, e.g. demo_app): " PACKAGE_NAME
if [[ ! "$PACKAGE_NAME" =~ ^[a-z][a-z0-9_]*$ ]]; then
  echo "Invalid package name. Use lowercase letters, digits, and underscores; must start with a letter." >&2
  exit 1
fi

read -r -p "Env var prefix for Dynaconf (e.g. DEMO): " ENV_PREFIX
if [[ ! "$ENV_PREFIX" =~ ^[A-Z][A-Z0-9_]*$ ]]; then
  echo "Invalid env prefix. Use UPPERCASE letters, digits, and underscores; must start with a letter." >&2
  exit 1
fi

# PascalCase for exception class name
PASCAL_NAME="$(python3 -c "
name = '${PACKAGE_NAME}'
print(''.join(part.capitalize() for part in name.split('_')))
")"

if [[ ! -d "src/${PLACEHOLDER_PKG}" ]]; then
  echo "Expected src/${PLACEHOLDER_PKG} not found. Already set up?" >&2
  exit 1
fi

mv "src/${PLACEHOLDER_PKG}" "src/${PACKAGE_NAME}"

# Replace package slug and PascalCase identifiers in text files
while IFS= read -r -d '' file; do
  sed -i.bak \
    -e "s/${PLACEHOLDER_PKG}/${PACKAGE_NAME}/g" \
    -e "s/${PLACEHOLDER_PASCAL}/${PASCAL_NAME}/g" \
    "$file"
  rm -f "${file}.bak"
done < <(find . \
  -type f \
  \( -name '*.py' -o -name '*.toml' -o -name '*.md' -o -name 'Dockerfile' -o -name 'Makefile' -o -name '*.sh' -o -name '*.example' -o -name '*.json' \) \
  ! -path './.git/*' \
  ! -path './.venv/*' \
  ! -path '*/__pycache__/*' \
  ! -name 'uv.lock' \
  -print0)

# Set Dynaconf envvar_prefix (only the config module token)
CONFIG_FILE="src/${PACKAGE_NAME}/config.py"
if [[ -f "$CONFIG_FILE" ]]; then
  sed -i.bak "s/envvar_prefix=\"${PLACEHOLDER_PREFIX}\"/envvar_prefix=\"${ENV_PREFIX}\"/" "$CONFIG_FILE"
  rm -f "${CONFIG_FILE}.bak"
fi

# Local settings for development
if [[ ! -f config/settings.local.json ]]; then
  if [[ -f config/settings.local.json.example ]]; then
    cp config/settings.local.json.example config/settings.local.json
    echo "Created config/settings.local.json from example."
  fi
fi

echo
echo "Setup complete."
echo "  Package:     ${PACKAGE_NAME}"
echo "  Env prefix:  ${ENV_PREFIX}"
echo
echo "Next:"
echo "  uv sync"
echo "  uv run ${PACKAGE_NAME}"
echo
echo "Env override example:"
echo "  ${ENV_PREFIX}_API__PORT=9000 uv run ${PACKAGE_NAME}"
