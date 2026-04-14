#!/usr/bin/env bash
set -euo pipefail

# build_macos.sh - package mdtopdf on macOS (Intel/Apple Silicon/universal2)
#
# Usage examples:
#   bash build_macos.sh
#   bash build_macos.sh --onedir
#   bash build_macos.sh --with-cli
#   bash build_macos.sh --target-arch universal2
#   bash build_macos.sh --python python3.12

ONEFILE=1
WITH_CLI=0
TARGET_ARCH="auto"   # auto | universal2 | arm64 | x86_64
PYTHON_BIN="python3"

usage() {
  cat <<'EOF'
Usage: build_macos.sh [options]

Options:
  --onedir                 Build as onedir (default: onefile)
  --onefile                Build as onefile
  --with-cli               Build CLI artifact in addition to GUI
  --target-arch <arch>     auto | universal2 | arm64 | x86_64 (default: auto)
  --python <bin>           Python executable (default: python3)
  -h, --help               Show this help
EOF
}

log() { echo "[build_macos] $*"; }
err() { echo "[build_macos][ERROR] $*" >&2; }

while [[ $# -gt 0 ]]; do
  case "$1" in
    --onedir)
      ONEFILE=0
      shift
      ;;
    --onefile)
      ONEFILE=1
      shift
      ;;
    --with-cli)
      WITH_CLI=1
      shift
      ;;
    --target-arch)
      TARGET_ARCH="${2:-}"
      shift 2
      ;;
    --python)
      PYTHON_BIN="${2:-}"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      err "Unknown argument: $1"
      usage
      exit 2
      ;;
  esac
done

if [[ "$(uname -s)" != "Darwin" ]]; then
  err "This script must run on macOS (Darwin)."
  exit 1
fi

case "$TARGET_ARCH" in
  auto|universal2|arm64|x86_64) ;;
  *)
    err "Invalid --target-arch: $TARGET_ARCH"
    exit 2
    ;;
esac

if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
  err "Python executable not found: $PYTHON_BIN"
  exit 1
fi

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DIST_DIR="$ROOT/dist"
BUILD_DIR="$ROOT/build"
ICON_ICNS="$ROOT/mdtopdf.icns"

DATA_FILES=(
  "$ROOT/mdtopdf/assets:mdtopdf/assets"
  "$ROOT/mdtopdf/config/default_config.yaml:mdtopdf/config"
)

HIDDEN_IMPORTS=(
  mdtopdf
  mdtopdf.gui
  mdtopdf.gui.app
  mdtopdf.gui.preview
  mdtopdf.core
  mdtopdf.core.parser
  mdtopdf.core.assembler
  mdtopdf.core.pdf_generator
  mdtopdf.core.previewer
  mdtopdf.core.renderer
  mdtopdf.core.renderer.base
  mdtopdf.core.renderer.plantuml_renderer
  mdtopdf.core.renderer.mermaid_renderer
  mdtopdf.config
  mdtopdf.config.config_loader
  mdtopdf.config.models
  mdtopdf.utils
  mdtopdf.utils.logger
  mdtopdf.utils.temp_manager
  mdtopdf.utils.file_utils
  weasyprint
  weasyprint.css
  weasyprint.document
  weasyprint.drawing
  weasyprint.fonts
  weasyprint.html
  weasyprint.images
  weasyprint.layout
  weasyprint.stacking
  weasyprint.text
  weasyprint.text.ffi
  weasyprint.text.fonts
  weasyprint.text.line_break
  fitz
  PIL
  PIL.Image
  PIL.ImageTk
  PIL._imaging
  pygments
  pygments.formatters
  pygments.formatters.html
  pygments.lexers
  pygments.lexers._mapping
  pygments.styles
  jinja2
  jinja2.ext
  yaml
  frontmatter
  cffi
  pydyf
  tinycss2
  tinyhtml5
  cssselect2
  pyphen
  fonttools
  zopfli
  brotli
)

COLLECT_ALL=(
  weasyprint
  pygments
  fitz
)

ensure_pyinstaller() {
  if ! "$PYTHON_BIN" -c "import PyInstaller" >/dev/null 2>&1; then
    log "PyInstaller not found. Installing..."
    "$PYTHON_BIN" -m pip install pyinstaller
  fi
}

check_weasyprint_import() {
  if ! "$PYTHON_BIN" -c "import weasyprint" >/dev/null 2>&1; then
    err "Cannot import weasyprint in current environment."
    err "Install dependencies first, e.g. pip install -r requirements.txt"
    exit 1
  fi
}

python_arches() {
  local py_exe
  py_exe="$($PYTHON_BIN -c 'import sys; print(sys.executable)')"

  if command -v lipo >/dev/null 2>&1; then
    local info
    info="$(lipo -info "$py_exe" 2>/dev/null || true)"
    if [[ "$info" == *"are:"* ]]; then
      # Example: Architectures in the fat file: ... are: x86_64 arm64
      echo "${info##*are: }"
      return 0
    fi
    if [[ "$info" == *"Non-fat file:"*"is architecture:"* ]]; then
      # Example: Non-fat file: ... is architecture: arm64
      echo "${info##*architecture: }"
      return 0
    fi
  fi

  "$PYTHON_BIN" -c 'import platform; print(platform.machine())'
}

has_arch() {
  local wanted="$1"
  local all="$2"
  for arch in $all; do
    if [[ "$arch" == "$wanted" ]]; then
      return 0
    fi
  done
  return 1
}

resolve_target_arch() {
  local arches
  arches="$(python_arches)"
  log "Detected Python architectures: $arches"

  if [[ "$TARGET_ARCH" == "auto" ]]; then
    if has_arch arm64 "$arches" && has_arch x86_64 "$arches"; then
      echo "universal2"
    elif has_arch arm64 "$arches"; then
      echo "arm64"
    elif has_arch x86_64 "$arches"; then
      echo "x86_64"
    else
      err "Unable to infer target arch from Python binary: $arches"
      exit 1
    fi
    return 0
  fi

  if [[ "$TARGET_ARCH" == "universal2" ]]; then
    if has_arch arm64 "$arches" && has_arch x86_64 "$arches"; then
      echo "universal2"
      return 0
    fi
    err "Requested universal2, but Python binary is not universal2: $arches"
    err "Use a universal2 Python and universal wheels, or build per-arch artifacts."
    exit 1
  fi

  # arm64 / x86_64
  if has_arch "$TARGET_ARCH" "$arches" || (has_arch arm64 "$arches" && has_arch x86_64 "$arches"); then
    echo "$TARGET_ARCH"
    return 0
  fi

  err "Requested --target-arch $TARGET_ARCH, but Python binary arches are: $arches"
  exit 1
}

run_pyinstaller() {
  local entry_point="$1"
  local app_name="$2"
  local windowed="$3"
  local effective_arch="$4"

  local -a cmd
  cmd=(
    "$PYTHON_BIN" -m PyInstaller
    "$entry_point"
    --name "$app_name"
    --clean
    --noconfirm
    "--distpath=$DIST_DIR"
    "--workpath=$BUILD_DIR"
    --target-arch "$effective_arch"
  )

  if [[ "$windowed" == "1" ]]; then
    cmd+=(--windowed)
  else
    cmd+=(--console)
  fi

  if [[ "$ONEFILE" == "1" ]]; then
    cmd+=(--onefile)
  else
    cmd+=(--onedir)
  fi

  if [[ -f "$ICON_ICNS" ]]; then
    cmd+=(--icon "$ICON_ICNS")
  fi

  local pair
  for pair in "${DATA_FILES[@]}"; do
    cmd+=(--add-data "$pair")
  done

  local hi
  for hi in "${HIDDEN_IMPORTS[@]}"; do
    cmd+=(--hidden-import "$hi")
  done

  local pkg
  for pkg in "${COLLECT_ALL[@]}"; do
    cmd+=(--collect-all "$pkg")
  done

  log "Running PyInstaller for $app_name"
  (cd "$ROOT" && "${cmd[@]}")
}

print_summary() {
  log "Build complete."
  if [[ "$ONEFILE" == "1" ]]; then
    if [[ -d "$DIST_DIR/mdtopdf-gui.app" ]]; then
      log "GUI app: $DIST_DIR/mdtopdf-gui.app"
    elif [[ -f "$DIST_DIR/mdtopdf-gui" ]]; then
      log "GUI binary: $DIST_DIR/mdtopdf-gui"
    else
      log "GUI artifact is under: $DIST_DIR"
    fi

    if [[ "$WITH_CLI" == "1" ]]; then
      if [[ -f "$DIST_DIR/mdtopdf" ]]; then
        log "CLI binary: $DIST_DIR/mdtopdf"
      else
        log "CLI artifact is under: $DIST_DIR"
      fi
    fi
  else
    log "Dist directory: $DIST_DIR"
  fi
}

main() {
  log "Root: $ROOT"
  log "Mode: $([[ "$ONEFILE" == "1" ]] && echo onefile || echo onedir)"

  ensure_pyinstaller
  check_weasyprint_import

  local effective_arch
  effective_arch="$(resolve_target_arch)"
  log "Target architecture: $effective_arch"

  run_pyinstaller "$ROOT/gui_entry.py" "mdtopdf-gui" "1" "$effective_arch"

  if [[ "$WITH_CLI" == "1" ]]; then
    local cli_entry
    cli_entry="$ROOT/cli_entry.py"
    cat > "$cli_entry" <<'PYEOF'
from mdtopdf.main import cli

if __name__ == "__main__":
    cli()
PYEOF
    trap 'rm -f "$ROOT/cli_entry.py"' EXIT

    run_pyinstaller "$cli_entry" "mdtopdf" "0" "$effective_arch"
    rm -f "$cli_entry"
    trap - EXIT
  fi

  print_summary
  log "Note: macOS still requires Cairo/Pango/GDK-PixBuf/libffi runtime libraries."
}

main

