import { z } from 'zod';
import type { AgentSSEEvent } from '@/types/event';
import { AgentMode, ResearchMode, SessionStatus } from '@/types/response';

export const AGENT_CONTRACT_VERSION = '2026-03-05.structured-output-v1';

const SessionStatusSchema = z.nativeEnum(SessionStatus);

const AgentModeSchema = z.nativeEnum(AgentMode);
const ResearchModeSchema = z.nativeEnum(ResearchMode);

const SandboxInfoSchema = z.object({
  sandbox_id: z.string(),
  streaming_mode: z.enum(['cdp_only']),
  status: z.string(),
});

const AgentEventEnvelopeSchema = z.custom<AgentSSEEvent>(
  (value) =>
    typeof value === 'object' &&
    value !== null &&
    'event' in value &&
    'data' in value,
);

export const CreateSessionResponseSchema = z.object({
  session_id: z.string(),
  mode: AgentModeSchema,
  research_mode: ResearchModeSchema,
  sandbox: SandboxInfoSchema.nullable(),
  status: SessionStatusSchema,
});

export const GetSessionResponseSchema = z.object({
  session_id: z.string(),
  title: z.string().nullable(),
  status: SessionStatusSchema,
  source: z.string(),
  research_mode: ResearchModeSchema,
  streaming_mode: z.enum(['cdp_only']).nullable(),
  events: z.array(AgentEventEnvelopeSchema),
  is_shared: z.boolean(),
});

const ListSessionItemSchema = z.object({
  session_id: z.string(),
  title: z.string().nullable(),
  latest_message: z.string().nullable(),
  latest_message_at: z.number().nullable(),
  status: SessionStatusSchema,
  unread_message_count: z.number(),
  is_shared: z.boolean(),
  source: z.string(),
});

export const ListSessionResponseSchema = z.object({
  sessions: z.array(ListSessionItemSchema),
});
