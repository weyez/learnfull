#!/bin/sh
set -eu

# Reuse ACCESS_KEY from the previous project, but never print it.
ACCESS_KEY=${ACCESS_KEY:-}
if [ "${#ACCESS_KEY}" -lt 16 ]; then
    echo 'ACCESS_KEY must be a secret of at least 16 characters.' >&2
    exit 1
fi

case "${PORT:-10000}" in
    ''|*[!0-9]*) echo 'PORT must be a number.' >&2; exit 1 ;;
esac
if [ "${PORT:-10000}" -lt 1024 ] || [ "${PORT:-10000}" -gt 65535 ]; then
    echo 'PORT must be between 1024 and 65535.' >&2
    exit 1
fi

export WEB_LISTENING_PORT="${PORT:-10000}"
export WEB_AUTHENTICATION=1
export WEB_AUTHENTICATION_USERNAME=ridfix
export WEB_AUTHENTICATION_PASSWORD="$ACCESS_KEY"
export WEB_AUTHENTICATION_TOKEN_VALIDITY_TIME=8
# Render terminates public HTTPS before forwarding to the private container.
# Do not expose this HTTP backend directly to an untrusted network.
export SECURE_CONNECTION=0
export WEB_AUTHENTICATION_ALLOW_INSECURE=1
export WEB_LOCALHOST_ONLY=0
export VNC_LOCALHOST_ONLY=1
unset ACCESS_KEY

echo "Starting authenticated browser service on port $WEB_LISTENING_PORT."
exec /init
