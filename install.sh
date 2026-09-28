#!/usr/bin/env sh
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
INSTALL_DIR=${SOONAI_INSTALL_DIR:-"${XDG_DATA_HOME:-$HOME/.local/share}/soonai"}
BIN_DIR=${SOONAI_BIN_DIR:-"$HOME/.local/bin"}
VENV_DIR="$INSTALL_DIR/.venv"

install_python_if_missing() {
    if command -v python3 >/dev/null 2>&1; then
        PYTHON_VERSION=$(python3 -c 'import sys; print("%s.%s" % (sys.version_info[0], sys.version_info[1]))')
        PYTHON_MAJOR=${PYTHON_VERSION%%.*}
        PYTHON_MINOR=${PYTHON_VERSION#*.}
        if [ "$PYTHON_MAJOR" -eq 3 ] && [ "$PYTHON_MINOR" -ge 12 ]; then
            PYTHON=$(command -v python3)
            return 0
        fi
    fi

    if command -v python >/dev/null 2>&1; then
        PYTHON_VERSION=$(python -c 'import sys; print("%s.%s" % (sys.version_info[0], sys.version_info[1]))')
        PYTHON_MAJOR=${PYTHON_VERSION%%.*}
        PYTHON_MINOR=${PYTHON_VERSION#*.}
        if [ "$PYTHON_MAJOR" -eq 3 ] && [ "$PYTHON_MINOR" -ge 12 ]; then
            PYTHON=$(command -v python)
            return 0
        fi
    fi

    OS_NAME=$(uname -s 2>/dev/null || echo unknown)
    echo "[INFO] Detected OS: $OS_NAME"

    case "$OS_NAME" in
        Darwin)
            if command -v brew >/dev/null 2>&1; then
                echo "[INFO] Python 3.12+ not found. Installing via Homebrew..."
                brew install python@3.12
                if command -v python3 >/dev/null 2>&1; then
                    PYTHON=$(command -v python3)
                    return 0
                fi
            fi
            ;;
        Linux)
            if [ -f /etc/os-release ]; then
                . /etc/os-release
                OS_ID=${ID:-unknown}
                OS_ID_LIKE=${ID_LIKE:-}
            else
                OS_ID=unknown
                OS_ID_LIKE=
            fi

            case "$OS_ID:$OS_ID_LIKE" in
                ubuntu:*|debian:*|linuxmint:*|pop:*)
                    echo "[INFO] Detected Debian-family distro. Installing Python 3.12 via apt..."
                    if command -v sudo >/dev/null 2>&1; then
                        sudo apt-get update
                        sudo apt-get install -y python3.12 python3.12-venv python3-pip
                    else
                        apt-get update
                        apt-get install -y python3.12 python3.12-venv python3-pip
                    fi
                    if command -v python3.12 >/dev/null 2>&1; then
                        PYTHON=$(command -v python3.12)
                        return 0
                    fi
                    ;;
                fedora:*|rhel:*|centos:*|rocky:*|almalinux:*)
                    echo "[INFO] Detected RHEL-family distro. Installing Python 3.12 via dnf..."
                    if command -v sudo >/dev/null 2>&1; then
                        sudo dnf install -y python3.12 python3.12-pip
                    else
                        dnf install -y python3.12 python3.12-pip
                    fi
                    if command -v python3.12 >/dev/null 2>&1; then
                        PYTHON=$(command -v python3.12)
                        return 0
                    fi
                    ;;
                arch:*|manjaro:*)
                    echo "[INFO] Detected Arch-family distro. Installing Python via pacman..."
                    if command -v sudo >/dev/null 2>&1; then
                        sudo pacman -Syu --noconfirm python python-pip
                    else
                        pacman -Syu --noconfirm python python-pip
                    fi
                    if command -v python >/dev/null 2>&1; then
                        PYTHON=$(command -v python)
                        return 0
                    fi
                    ;;
                opensuse*|sles*|sled*)
                    echo "[INFO] Detected SUSE-family distro. Installing Python 3.12 via zypper..."
                    if command -v sudo >/dev/null 2>&1; then
                        sudo zypper install -y python312 python312-pip
                    else
                        zypper install -y python312 python312-pip
                    fi
                    if command -v python3.12 >/dev/null 2>&1; then
                        PYTHON=$(command -v python3.12)
                        return 0
                    fi
                    ;;
                alpine:*)
                    echo "[INFO] Detected Alpine distro. Installing Python via apk..."
                    if command -v sudo >/dev/null 2>&1; then
                        sudo apk add --no-cache python3 py3-pip
                    else
                        apk add --no-cache python3 py3-pip
                    fi
                    if command -v python3 >/dev/null 2>&1; then
                        PYTHON=$(command -v python3)
                        return 0
                    fi
                    ;;
                *)
                    echo "[INFO] Generic Linux detected. Trying apt-get as fallback..."
                    if command -v sudo >/dev/null 2>&1; then
                        sudo apt-get update
                        sudo apt-get install -y python3.12 python3.12-venv python3-pip
                    elif command -v apt-get >/dev/null 2>&1; then
                        apt-get update
                        apt-get install -y python3.12 python3.12-venv python3-pip
                    elif command -v dnf >/dev/null 2>&1; then
                        dnf install -y python3.12 python3.12-pip
                    elif command -v pacman >/dev/null 2>&1; then
                        pacman -Syu --noconfirm python python-pip
                    else
                        echo "[ERROR] Unsupported Linux distro for automatic Python install." >&2
                        exit 1
                    fi
                    if command -v python3.12 >/dev/null 2>&1; then
                        PYTHON=$(command -v python3.12)
                        return 0
                    fi
                    ;;
            esac
            ;;
        *)
            echo "[ERROR] Unsupported OS: $OS_NAME. Please install Python 3.12+ manually." >&2
            exit 1
            ;;
    esac

    echo "[ERROR] Python 3.12 or newer was not found and automatic installation failed." >&2
    exit 1
}

install_python_if_missing

if [ -x "$SCRIPT_DIR/.venv/bin/python" ]; then
    PYTHON="$SCRIPT_DIR/.venv/bin/python"
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

for file in soonai.py requirements.txt soonai.spec README.md; do
    cp "$SCRIPT_DIR/$file" "$INSTALL_DIR/$file"
done

# คัดลอก shared/ โดยเว้น "ความลับกับค่าส่วนตัวของผู้พัฒนา" และของที่เครื่องปลายทางสร้างเอง
# (keys.json/config.json/team.json/mcp.json = ของผู้ใช้ · *.default.json ต้องคัดลอก
#  เพราะ runtime.ensure_user_files() ใช้เป็นต้นแบบตอนสร้างไฟล์ที่ DATA_DIR ครั้งแรก)
mkdir -p "$INSTALL_DIR/shared"
(
    cd "$SCRIPT_DIR/shared" &&
    find . \
        -name '__pycache__' -prune -o \
        -name 'keys.json' -prune -o \
        -name 'config.json' -prune -o \
        -name 'team.json' -prune -o \
        -name 'mcp.json' -prune -o \
        -name '.machine_id' -prune -o \
        -name '.models_cache.json' -prune -o \
        -type f -print
) | while IFS= read -r relative; do
    relative=${relative#./}
    destination="$INSTALL_DIR/shared/$relative"
    mkdir -p "$(dirname "$destination")"
    cp "$SCRIPT_DIR/shared/$relative" "$destination"
done

cat > "$BIN_DIR/soonai" <<EOF
#!/usr/bin/env sh
# บังคับ UTF-8: ทุกข้อความ UI เป็นภาษาไทย ถ้า locale ไม่ใช่ UTF-8 จะ UnicodeEncodeError
PYTHONUTF8=1
PYTHONIOENCODING=utf-8
export PYTHONUTF8 PYTHONIOENCODING
exec "$VENV_DIR/bin/python" "$INSTALL_DIR/soonai.py" "\$@"
EOF
chmod +x "$BIN_DIR/soonai"

PATH_LINE="export PATH=\"$BIN_DIR:\$PATH\""
PATH_UPDATED=0
for profile in "$HOME/.profile" "$HOME/.zprofile"; do
    if { [ -f "$profile" ] && [ -w "$profile" ]; } ||
        { [ ! -e "$profile" ] && [ -w "$HOME" ]; }; then
        if ! grep -Fqx "$PATH_LINE" "$profile" 2>/dev/null; then
            printf '\n# SoonAI\n%s\n' "$PATH_LINE" >> "$profile"
        fi
        PATH_UPDATED=1
    fi
done

echo "[OK] SoonAI ติดตั้งสำเร็จที่ $INSTALL_DIR"
if [ "$PATH_UPDATED" -eq 1 ]; then
    echo "[INFO] เปิด terminal ใหม่แล้วใช้คำสั่ง: soonai"
else
    echo "[INFO] เรียกใช้ด้วย: $BIN_DIR/soonai"
    echo "[INFO] หรือเพิ่ม $BIN_DIR ลง PATH ของ shell เอง"
fi
