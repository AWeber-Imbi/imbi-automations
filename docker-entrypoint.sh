#!/bin/bash
set -e

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
    echo "Configuring git commit signing with SSH key: $SSH_KEY_PATH"
    git config --global gpg.format ssh
    git config --global user.signingkey "${SSH_KEY_PATH}.pub"
    git config --global commit.gpgsign true
    git config --global tag.gpgsign true

    # Create allowed_signers file for verification
    SIGNERS_FILE=~/.ssh/allowed_signers
    if [ ! -f "$SIGNERS_FILE" ]; then
        echo "${GIT_USER_EMAIL} $(cat "${SSH_KEY_PATH}.pub")" > "$SIGNERS_FILE"
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
