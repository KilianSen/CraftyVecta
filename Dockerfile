# syntax=docker/dockerfile:1.7
# CraftyVecta: the official Crafty image plus the vecta server jar and the
# craftyvecta hook. Needs the vecta sources as the "vecta" build context
# (compose.yaml sets it), e.g.:
#   docker build --build-context vecta=https://github.com/KilianSen/vecta.git#master -t craftyvecta .
ARG CRAFTY_VERSION=4.10.8

# The jar is Java 8 bytecode for every platform: build it natively, not emulated.
FROM --platform=$BUILDPLATFORM eclipse-temurin:21-jdk AS jar
ARG VECTA_VERSION=0.1.0
COPY --from=vecta plugins/universal /src
RUN VERSION="$VECTA_VERSION" sh /src/build.sh

FROM registry.gitlab.com/crafty-controller/crafty-4:${CRAFTY_VERSION}
COPY --from=jar --chown=crafty:root /src/build/vecta.jar /crafty/vecta/vecta.jar
COPY --chown=crafty:root craftyvecta /crafty/vecta/craftyvecta
# New files next to Crafty's static assets, for the "with vecta" badge.
COPY --chown=crafty:root craftyvecta/static/vecta /crafty/app/frontend/static/assets/vecta

# Crafty's launcher starts Python through `sudo -u crafty`, so keep VECTA_*
# across sudo's env_reset. Crafty's interpreter reads craftyvecta.pth at
# startup: the first line puts the package on sys.path, the second installs
# the hook. The last command checks both the way Crafty starts: through sudo,
# with exactly one hook, holding the token.
RUN printf 'Defaults env_keep += "VECTA_*"\n' > /etc/sudoers.d/craftyvecta \
 && chmod 0440 /etc/sudoers.d/craftyvecta \
 && site="$(/crafty/.venv/bin/python3 -c 'import sysconfig; print(sysconfig.get_paths()["purelib"])')" \
 && printf '/crafty/vecta\nimport craftyvecta.hook; craftyvecta.hook.install()\n' > "$site/craftyvecta.pth" \
 && cd /crafty \
 && VECTA_TOKEN=kept sudo -u crafty /crafty/.venv/bin/python3 -c 'import sys, craftyvecta.hook as h; f = [x for x in sys.meta_path if isinstance(x, h._Finder)]; assert len(f) == 1 and f[0].settings.token == "kept", [x.settings.token for x in f]'

LABEL org.opencontainers.image.title="CraftyVecta" \
      org.opencontainers.image.description="Crafty Controller with the vecta gateway integration" \
      org.opencontainers.image.licenses="GPL-3.0"
