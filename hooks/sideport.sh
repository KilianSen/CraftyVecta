#!/bin/sh
# Side port hook for every Crafty server (sidePortHook in the jar's config).
# CraftyVecta's own voice port goes to vecta's Simple Voice Chat hook; any
# other side port goes to the server's own hook, given as arguments
# (sidePortHook in vecta.override.properties). Runs in the server directory.
set -eu

if [ "$VECTA_SIDEPORT_NAME" = voicechat ]; then
  exec sh "$(dirname "$0")/simple-voice-chat.sh"
fi
if [ "$#" -eq 0 ]; then
  echo "no sidePortHook in vecta.override.properties for side port $VECTA_SIDEPORT_NAME ($VECTA_SIDEPORT_STATE)"
  exit 0
fi
exec "$@"
