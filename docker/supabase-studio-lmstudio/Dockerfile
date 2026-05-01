FROM public.ecr.aws/supabase/studio:2026.04.27-sha-4afbe9c

COPY patch-studio-lmstudio.js /tmp/patch-studio-lmstudio.js
RUN node /tmp/patch-studio-lmstudio.js && rm /tmp/patch-studio-lmstudio.js
