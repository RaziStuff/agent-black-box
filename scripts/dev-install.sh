#!/usr/bin/env sh
set -eu

ROOT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
VENV_DIR="${ABB_VENV:-"$ROOT_DIR/.venv"}"
PYTHON_BIN="${PYTHON:-python3}"

printf 'Agent Black Box dev install\n'
printf 'Root: %s\n' "$ROOT_DIR"
printf 'Virtualenv: %s\n' "$VENV_DIR"

if [ ! -d "$VENV_DIR" ]; then
  "$PYTHON_BIN" -m venv "$VENV_DIR"
fi

VENV_PYTHON="$VENV_DIR/bin/python"
VENV_ABB="$VENV_DIR/bin/abb"

export PIP_CACHE_DIR="$ROOT_DIR/.pip-cache"
export PIP_DISABLE_PIP_VERSION_CHECK=1
PIP_LOG="$ROOT_DIR/.pip-install.log"

if "$VENV_PYTHON" -m pip install --no-build-isolation --editable "$ROOT_DIR" > "$PIP_LOG" 2>&1; then
  INSTALL_MODE="editable package"
else
  INSTALL_MODE="local path shim"
  printf 'Editable install unavailable; using local path shim. Details: %s\n' "$PIP_LOG"
  SITE_PACKAGES="$("$VENV_PYTHON" -c 'import site; print(site.getsitepackages()[0])')"
  printf '%s\n' "$ROOT_DIR/src" > "$SITE_PACKAGES/agent_black_box_dev.pth"
  {
    printf '%s\n' '#!/usr/bin/env sh'
    printf 'PYTHONPATH="%s${PYTHONPATH:+:$PYTHONPATH}" exec "%s" -m agent_black_box "$@"\n' "$ROOT_DIR/src" "$VENV_PYTHON"
  } > "$VENV_ABB"
  chmod +x "$VENV_ABB"
fi

"$VENV_ABB" --help >/dev/null
"$VENV_ABB" doctor

cat <<EOF

Installed Agent Black Box CLI using: $INSTALL_MODE.

Try:
  "$VENV_ABB" record -- python3 examples/basic_agent.py
  "$VENV_ABB" runs
  "$VENV_ABB" start

After activation:
  abb record -- python3 examples/basic_agent.py
  abb runs
  abb start

To activate:
  . "$VENV_DIR/bin/activate"
EOF
