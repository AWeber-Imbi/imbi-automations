#!/bin/bash
set -e

# --- Initialization Directory Processing ---
# Similar to database images' /docker-entrypoint-initdb.d pattern
# Supports: .apt (system packages), .pip (pip packages), .sh (scripts)
# Files are processed in sorted order (use numeric prefixes for ordering)
INIT_DIR="/docker-entrypoint-init.d"

if [ -d "$INIT_DIR" ] && [ "$(ls -A $INIT_DIR 2>/dev/null)" ]; then
    echo "Processing initialization files from $INIT_DIR..."

    # Collect files by type
    APT_PACKAGES=""
    PIP_FILES=""
    SH_FILES=""

    for f in $(find "$INIT_DIR" -maxdepth 1 -type f | sort); do
        case "$f" in
            *.apt)
                echo "  Found apt package list: $f"
                # Filter out comments and empty lines, collect packages
                APT_PACKAGES="$APT_PACKAGES $(grep -v '^\s*#' "$f" | grep -v '^\s*$' | tr '\n' ' ')"
                ;;
            *.pip)
                echo "  Found pip requirements: $f"
                PIP_FILES="$PIP_FILES $f"
                ;;
            *.sh)
                echo "  Found shell script: $f"
                SH_FILES="$SH_FILES $f"
                ;;
            *)
                echo "  Skipping unknown file type: $f"
                ;;
        esac
    done

    # Install apt packages (batch for efficiency)
    if [ -n "$APT_PACKAGES" ]; then
        echo "Installing system packages: $APT_PACKAGES"
        sudo apt-get update
        sudo apt-get install -y --no-install-recommends $APT_PACKAGES
        sudo apt-get clean
        sudo rm -rf /var/lib/apt/lists/*
    fi

    # Install pip packages
    for f in $PIP_FILES; do
        echo "Installing pip packages from: $f"
        pip install --user --no-cache-dir -r "$f"
    done

    # Run shell scripts
    for f in $SH_FILES; do
        echo "Running script: $f"
        bash "$f"
    done

    echo "Initialization complete."
fi

# --- Git SSH Commit Signing ---
# Auto-detect SSH key and configure git signing if found
SSH_KEY_PATH=""
for key in ~/.ssh/id_ed25519 ~/.ssh/id_rsa ~/.ssh/id_ecdsa; do
    if [ -f "$key" ]; then
        SSH_KEY_PATH="$key"
        break
    fi
done

if [ -n "$SSH_KEY_PATH" ]; then
    PUB_KEY_PATH="${SSH_KEY_PATH}.pub"

    # Generate public key from private key if it doesn't exist
    # Use a temp location since .ssh may be mounted read-only
    if [ ! -f "$PUB_KEY_PATH" ]; then
        TEMP_PUB_KEY="/tmp/ssh_signing_key.pub"
        echo "Generating public key from $SSH_KEY_PATH..."
        if ssh-keygen -y -f "$SSH_KEY_PATH" > "$TEMP_PUB_KEY" 2>/dev/null; then
            PUB_KEY_PATH="$TEMP_PUB_KEY"
        fi
    fi

    if [ -f "$PUB_KEY_PATH" ]; then
        echo "Configuring git commit signing with SSH key: $SSH_KEY_PATH"
        git config --global gpg.format ssh
        git config --global user.signingkey "$PUB_KEY_PATH"
        git config --global commit.gpgsign true
        git config --global tag.gpgsign true

        # Create allowed_signers file for verification (use temp if .ssh is read-only)
        SIGNERS_FILE=~/.ssh/allowed_signers
        if [ ! -f "$SIGNERS_FILE" ]; then
            SIGNERS_FILE="/tmp/allowed_signers"
            echo "${GIT_USER_EMAIL} $(cat "$PUB_KEY_PATH")" > "$SIGNERS_FILE"
        fi
        git config --global gpg.ssh.allowedSignersFile "$SIGNERS_FILE"
    fi
fi

# --- GitHub CLI Authentication ---
# Option 1: GH_TOKEN environment variable (already works natively)
# Option 2: Token file at /config/gh-token or ~/.config/gh/token
if [ -z "$GH_TOKEN" ]; then
    for token_file in /config/gh-token ~/.config/gh/token; do
        if [ -f "$token_file" ]; then
            export GH_TOKEN=$(cat "$token_file")
            echo "Loaded GitHub token from $token_file"
            break
        fi
    done
fi

# Execute the main command
exec "$@"
