#!/bin/bash
set -e

source /home/imbi-automations/.profile

# --- Required Environment Variables ---
# Check that required environment variables are set
MISSING_VARS=""

if [ -z "$ANTHROPIC_API_KEY" ] || [ "$ANTHROPIC_API_KEY" = "unspecified" ]; then
    MISSING_VARS="$MISSING_VARS ANTHROPIC_API_KEY"
fi

if [ -z "$IMBI_API_KEY" ] || [ "$IMBI_API_KEY" = "unspecified" ]; then
    MISSING_VARS="$MISSING_VARS IMBI_API_KEY"
fi

if [ -z "$GH_TOKEN" ] || [ "$GH_TOKEN" = "unspecified" ]; then
    MISSING_VARS="$MISSING_VARS GH_TOKEN"
fi

if [ -n "$MISSING_VARS" ]; then
    echo "Error: Required environment variables are not set:$MISSING_VARS" >&2
    exit 1
fi

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
        sudo apt-get update >> /opt/logs/entrypoint.log 2>&1
        sudo apt-get install -y --no-install-recommends $APT_PACKAGES >> /opt/logs/entrypoint.log 2>&1
        sudo apt-get clean >> /opt/logs/entrypoint.log 2>&1
        sudo rm -rf /var/lib/apt/lists/*
    fi

    # Install pip packages
    for f in $PIP_FILES; do
        echo "Installing pip packages from: $f"
        pip install --user --no-cache-dir -r "$f" >> /opt/logs/entrypoint.log 2>&1
    done

    # Run shell scripts
    for f in $SH_FILES; do
        echo "Running script: $f"
        bash "$f"
    done

    echo "Initialization complete."
fi

# Re-source .profile if init scripts modified it (e.g., PATH updates)
if [ -f ~/.profile ]; then
    source ~/.profile
fi

# --- Git Configuration ---
# Configure git user identity from environment variables
if [ -n "$GIT_USER_NAME" ]; then
    git config --global user.name "$GIT_USER_NAME"
fi
if [ -n "$GIT_USER_EMAIL" ]; then
    git config --global user.email "$GIT_USER_EMAIL"
fi

# --- SSH Configuration ---
# Auto-detect SSH key and configure for git operations
# Copy keys to writable location since mounted .ssh may be read-only
MOUNTED_SSH_KEY=""
for key in ~/.ssh/id_ed25519 ~/.ssh/id_rsa ~/.ssh/id_ecdsa; do
    if [ -f "$key" ]; then
        MOUNTED_SSH_KEY="$key"
        break
    fi
done

SSH_KEY_PATH=""
if [ -n "$MOUNTED_SSH_KEY" ]; then
    # Create writable .ssh directory and copy keys with correct permissions
    SSH_DIR=~/.ssh-runtime
    mkdir -p "$SSH_DIR"
    chmod 700 "$SSH_DIR"

    KEY_NAME=$(basename "$MOUNTED_SSH_KEY")
    cp "$MOUNTED_SSH_KEY" "$SSH_DIR/$KEY_NAME"
    chmod 600 "$SSH_DIR/$KEY_NAME"
    SSH_KEY_PATH="$SSH_DIR/$KEY_NAME"

    if [ -f "${MOUNTED_SSH_KEY}.pub" ]; then
        cp "${MOUNTED_SSH_KEY}.pub" "$SSH_DIR/${KEY_NAME}.pub"
        chmod 644 "$SSH_DIR/${KEY_NAME}.pub"
    fi

    # Copy config if present
    if [ -f ~/.ssh/config ]; then
        cp ~/.ssh/config "$SSH_DIR/config"
        chmod 600 "$SSH_DIR/config"
    fi

    # Create SSH config to use our runtime directory
    cat > "$SSH_DIR/config" <<EOF
Host *
    IdentityFile $SSH_KEY_PATH
    UserKnownHostsFile $SSH_DIR/known_hosts
    StrictHostKeyChecking accept-new
EOF

    # Add GitHub hosts to known_hosts
	ssh-keyscan -t ed25519,rsa "github.com" >> "$SSH_DIR/known_hosts" 2>/dev/null || true

    # Scan GHE host if GITHUB_HOSTNAME is set (strip api. prefix if present)
    if [ -n "$GITHUB_HOSTNAME" ]; then
        GHE_HOST=$(echo "$GITHUB_HOSTNAME" | sed 's/^api\.//')
        ssh-keyscan -t ed25519,rsa "$GHE_HOST" >> "$SSH_DIR/known_hosts" 2>/dev/null || true
    fi

    # Point SSH to our runtime config
    export GIT_SSH_COMMAND="ssh -F $SSH_DIR/config"
    echo "Configured SSH with key: $SSH_KEY_PATH"
fi

if [ -n "$SSH_KEY_PATH" ] && [ -f "${SSH_KEY_PATH}.pub" ]; then
    echo "Configuring git commit signing with SSH key: $SSH_KEY_PATH"
    git config --global gpg.format ssh
    git config --global user.signingkey "${SSH_KEY_PATH}.pub"
    git config --global commit.gpgsign true
    git config --global tag.gpgsign true

    # Create allowed_signers file for verification
    SIGNERS_FILE="$SSH_DIR/allowed_signers"
    echo "${GIT_USER_EMAIL} $(cat "${SSH_KEY_PATH}.pub")" > "$SIGNERS_FILE"
    git config --global gpg.ssh.allowedSignersFile "$SIGNERS_FILE"
fi

# Execute the main command
exec "$@"
