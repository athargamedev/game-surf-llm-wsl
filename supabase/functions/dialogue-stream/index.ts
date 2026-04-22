import { serve } from "https://deno.land/std@0.208.0/http/server.ts";
import { createClient } from "https://esm.sh/@supabase/supabase-js@2";
import { SupabaseClient } from "https://esm.sh/@supabase/supabase-js@2";

const supabaseUrl = Deno.env.get("SUPABASE_URL")!;
const supabaseServiceKey = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!;

interface DialogueTurn {
  session_id: string;
  player_id: string;
  npc_id: string;
  player_message: string;
  stream_response?: boolean;
}

interface StreamResponse {
  success: boolean;
  session_id?: string;
  turn_id?: number;
  npc_response?: string;
  finished?: boolean;
  error?: string;
}

async function getNPCProfile(client: SupabaseClient, npcId: string) {
  const { data, error } = await client.rpc("get_npc_profile", { target_npc_id: npcId });
  if (error || !data || data.length === 0) return null;
  return data[0];
}

async function getMemoryContext(client: SupabaseClient, playerId: string, npcId: string) {
  const { data, error } = await client.rpc("get_memory_context", {
    target_player_id: playerId,
    target_npc_id: npcId,
    memory_limit: 3,
  });
  if (error || !data || data.length === 0) return null;
  return data[0];
}

async function createTurn(
  client: SupabaseClient,
  sessionId: string,
  playerId: string,
  npcId: string,
  playerMessage: string,
  npcResponse: string
) {
  const { data, error } = await client
    .from("dialogue_turns")
    .insert({
      session_id: sessionId,
      player_message: playerMessage,
      npc_response: npcResponse,
      raw_json: {
        player_id: playerId,
        npc_id: npcId,
      },
    })
    .select()
    .single();

  if (error) {
    console.error("Error creating turn:", error);
    return null;
  }
  return data;
}

async function updateSessionStats(client: SupabaseClient, sessionId: string) {
  const { count } = await client
    .from("dialogue_turns")
    .select("*", { count: "exact", head: true })
    .eq("session_id", sessionId);

  if (count !== null) {
    await client
      .from("dialogue_sessions")
      .update({ turn_count: count })
      .eq("session_id", sessionId);
  }
}

async function getOrCreateSession(
  client: SupabaseClient,
  playerId: string,
  npcId: string
): Promise<string | null> {
  // Check for active session
  const { data: existing } = await client
    .from("dialogue_sessions")
    .select("session_id")
    .eq("player_id", playerId)
    .eq("npc_id", npcId)
    .eq("status", "active")
    .single();

  if (existing) {
    return existing.session_id;
  }

  // Create new session
  const { data: newSession, error } = await client
    .from("dialogue_sessions")
    .insert({
      player_id: playerId,
      npc_id: npcId,
      status: "active",
      started_at: new Date().toISOString(),
    })
    .select("session_id")
    .single();

  if (error) {
    console.error("Error creating session:", error);
    return null;
  }

  return newSession?.session_id || null;
}

serve(async (req: Request): Promise<Response> => {
  // CORS headers
  if (req.method === "OPTIONS") {
    return new Response("ok", {
      headers: {
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Methods": "POST, OPTIONS",
        "Access-Control-Allow-Headers": "Content-Type, Authorization",
      },
    });
  }

  if (req.method !== "POST") {
    return new Response(
      JSON.stringify({ success: false, error: "Method not allowed" }),
      { status: 405, headers: { "Content-Type": "application/json" } }
    );
  }

  try {
    const supabase = createClient(supabaseUrl, supabaseServiceKey);
    const body: DialogueTurn = await req.json();

    const { session_id, player_id, npc_id, player_message } = body;

    if (!player_id || !npc_id || !player_message) {
      return new Response(
        JSON.stringify({ success: false, error: "Missing required fields" }),
        { status: 400, headers: { "Content-Type": "application/json" } }
      );
    }

    // Get or create session
    const sessionId = await getOrCreateSession(supabase, player_id, npc_id);
    if (!sessionId) {
      return new Response(
        JSON.stringify({ success: false, error: "Failed to create session" }),
        { status: 500, headers: { "Content-Type": "application/json" } }
      );
    }

    // Get NPC profile
    const npcProfile = await getNPCProfile(supabase, npc_id);

    // Get memory context
    const memoryContext = await getMemoryContext(supabase, player_id, npc_id);

    // Build prompt context
    let contextPrompt = "";
    if (npcProfile) {
      contextPrompt += `You are ${npcProfile.display_name}. `;
      contextPrompt += `Your subject: ${npcProfile.subject}. `;
      if (npcProfile.personality?.tone) {
        contextPrompt += `Tone: ${npcProfile.personality.tone}. `;
      }
      if (npcProfile.voice_rules && npcProfile.voice_rules.length > 0) {
        contextPrompt += `Rules: ${npcProfile.voice_rules.join(", ")}. `;
      }
    }
    if (memoryContext?.summary) {
      contextPrompt += `\n\nPrevious conversations summary: ${memoryContext.summary}`;
    }

    // Fetch dialogue history for context
    const { data: history } = await supabase
      .from("dialogue_turns")
      .select("player_message, npc_response")
      .eq("session_id", sessionId)
      .order("created_at", { ascending: true })
      .limit(10);

    // Build history string
    let historyStr = "";
    if (history && history.length > 0) {
      historyStr = history
        .map((h) => `Player: ${h.player_message}\nNPC: ${h.npc_response}`)
        .join("\n\n");
    }

    // Call AI (placeholder - integrate with your LLM)
    // For now, return a placeholder response
    const npcResponse = npcProfile
      ? `[${npcProfile.display_name}]: Thank you for your message about "${player_message.substring(0, 50)}...". This is a placeholder response - integrate your LLM here.`
      : "NPC response placeholder - integrate your LLM here.";

    // Create dialogue turn
    const turn = await createTurn(
      supabase,
      sessionId,
      player_id,
      npc_id,
      player_message,
      npcResponse
    );

    // Update session turn count
    await updateSessionStats(supabase, sessionId);

    const response: StreamResponse = {
      success: true,
      session_id: sessionId,
      turn_id: turn?.id || 0,
      npc_response: npcResponse,
      finished: true,
    };

    return new Response(JSON.stringify(response), {
      status: 200,
      headers: {
        "Content-Type": "application/json",
        "Access-Control-Allow-Origin": "*",
      },
    });
  } catch (err) {
    console.error("Error:", err);
    return new Response(
      JSON.stringify({ success: false, error: err.message }),
      { status: 500, headers: { "Content-Type": "application/json" } }
    );
  }
});
