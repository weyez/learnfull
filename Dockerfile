# Upstream Firefox desktop + browser-based display/audio streaming.
# latest is intentional: old releases may lack the authentication/audio features.
FROM jlesage/firefox:latest

# Fail closed if the pulled upstream image lacks the documented web-login feature.
RUN test -x /init && grep -R -q 'WEB_AUTHENTICATION' /etc/cont-init.d /etc/services.d /etc/cont-env.d

COPY launch.sh /window-launch.sh
RUN chmod 0755 /window-launch.sh

ENV APP_NAME="Window Browser" \
    DISPLAY_WIDTH="1024" \
    DISPLAY_HEIGHT="640" \
    WEB_AUDIO="1" \
    WEB_FILE_MANAGER="0" \
    WEB_TERMINAL="0" \
    WEB_HOST_CLIPBOARD_SYNC="0" \
    KEEP_APP_RUNNING="1" \
    FF_PREF_PROCESSES="dom.ipc.processCount=1" \
    FF_PREF_ISOLATED_PROCESSES="dom.ipc.processCount.webIsolated=1" \
    FF_PREF_MEMORY_CACHE="browser.cache.memory.capacity=16384" \
    FF_PREF_HOME='browser.startup.homepage="about:blank"'

EXPOSE 10000
ENTRYPOINT ["/window-launch.sh"]
