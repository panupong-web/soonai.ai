#!/usr/bin/env sh
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
INSTALL_DIR=${SOONAI_INSTALL_DIR:-"${XDG_DATA_HOME:-$HOME/.local/share}/soonai"}
BIN_DIR=${SOONAI_BIN_DIR:-"$HOME/.local/bin"}
VENV_DIR="$INSTALL_DIR/.venv"

if [ -x "$SCRIPT_DIR/.venv/bin/python" ]; then
    PYTHON="$SCRIPT_DIR/.venv/bin/python"
elif command -v python3 >/dev/null 2>&1; then
    PYTHON=$(command -v python3)
elif command -v python >/dev/null 2>&1; then
    PYTHON=$(command -v python)
else
    echo "[ERROR] Python 3 was not found. Install it with your system package manager." >&2
    exit 1
fi

PYTHON_VERSION=$("$PYTHON" -c 'import sys; print("%s.%s" % (sys.version_info[0], sys.version_info[1]))')
PYTHON_MAJOR=${PYTHON_VERSION%%.*}
PYTHON_MINOR=${PYTHON_VERSION#*.}
if [ "$PYTHON_MAJOR" -ne 3 ] || [ "$PYTHON_MINOR" -lt 12 ]; then
    echo "[ERROR] SoonAI requires Python 3.12 or newer (found $PYTHON_VERSION)." >&2
    exit 1
fi

mkdir -p "$INSTALL_DIR" "$BIN_DIR"
if [ ! -x "$VENV_DIR/bin/python" ]; then
    "$PYTHON" -m venv "$VENV_DIR"
fi

"$VENV_DIR/bin/python" -m pip install --upgrade pip
"$VENV_DIR/bin/python" -m pip install -r "$SCRIPT_DIR/requirements.txt"

for file in soonai.py soonai_custom.py requirements.txt soonai.spec README.md; do
    cp "$SCRIPT_DIR/$file" "$INSTALL_DIR/$file"
done
for directory in shared apps packages; do
    mkdir -p "$INSTALL_DIR/$directory"
    cp -R "$SCRIPT_DIR/$directory/." "$INSTALL_DIR/$directory/"
done

cat > "$BIN_DIR/soonai" <<EOF
#!/usr/bin/env sh
exec "$VENV_DIR/bin/python" "$INSTALL_DIR/soonai.py" "\$@"
EOF
chmod +x "$BIN_DIR/soonai"

case ":${PATH}:" in
    *:"$BIN_DIR":*) ;;
    *) echo "[INFO] เพิ่ม $BIN_DIR ลง PATH ใน shell profile ของคุณเพื่อเรียกใช้ 'soonai' ได้ทุกที่" ;;
esac

echo "[OK] SoonAI ติดตั้งสำเร็จที่ $INSTALL_DIR"
echo "[INFO] เปิด terminal ใหม่แล้วใช้คำสั่ง: soonai"
