FROM public.ecr.aws/supabase/studio:2026.04.27-sha-4afbe9c

COPY patch-studio-lmstudio.js /tmp/patch-studio-lmstudio.js
RUN node /tmp/patch-studio-lmstudio.js && rm /tmp/patch-studio-lmstudio.js

COPY runtime-configure-studio.js /usr/local/bin/runtime-configure-studio.js
COPY entrypoint-lmstudio.sh /usr/local/bin/entrypoint-lmstudio.sh
RUN chmod +x /usr/local/bin/entrypoint-lmstudio.sh

ENTRYPOINT ["/usr/local/bin/entrypoint-lmstudio.sh"]
CMD ["node","apps/studio/server.js"]
