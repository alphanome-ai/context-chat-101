import { z } from "zod";

export const errorResponseSchema = z.object({
  error: z.object({ message: z.string().optional() }).optional(),
  detail: z.union([z.string(), z.array(z.unknown())]).optional(),
});

export const authFormSchema = z.object({
  email: z.email("Enter a valid email address."),
  password: z.string().min(8, "Password must be at least 8 characters."),
});

export const userSchema = z.object({
  id: z.number(),
  email: z.string(),
  created_at: z.string(),
});

export const authResponseSchema = z.object({
  token: z.string(),
  user: userSchema,
});

export const llmModelSchema = z.object({
  id: z.string(),
  name: z.string().nullable().optional(),
  displayName: z.string().nullable().optional(),
  isDefault: z.boolean().optional(),
});

export const providersResponseSchema = z.object({
  providers: z
    .array(
      z.object({
        name: z.string(),
        models: z.array(llmModelSchema),
      }),
    )
    .optional(),
});

export const assistantResponseMessageSchema = z.object({
  content: z.string().nullable().optional(),
  reasoning: z.string().nullable().optional(),
  reasoningContent: z.string().nullable().optional(),
  reasoning_content: z.string().nullable().optional(),
  thinking: z.string().nullable().optional(),
});

export const tokenUsageSchema = z.object({
  input_tokens: z.number(),
  output_tokens: z.number(),
  total_tokens: z.number(),
});

export const chatCompletionResponseSchema = z.object({
  choices: z
    .array(
      z.object({
        message: assistantResponseMessageSchema.optional(),
      }),
    )
    .optional(),
  usage: tokenUsageSchema.nullable().optional(),
  error: z.object({ message: z.string().optional() }).optional(),
});

export const chatCompletionChunkSchema = z.object({
  choices: z
    .array(
      z.object({
        delta: assistantResponseMessageSchema.optional(),
      }),
    )
    .optional(),
  usage: tokenUsageSchema.nullable().optional(),
  error: z.object({ message: z.string().optional() }).optional(),
});

export const chatSessionSummarySchema = z.object({
  id: z.number(),
  title: z.string(),
  model: z.string().nullable().optional(),
  created_at: z.string(),
  updated_at: z.string(),
  message_count: z.number(),
});

export const chatSessionDetailSchema = z.object({
  id: z.number(),
  title: z.string(),
  model: z.string().nullable().optional(),
  created_at: z.string(),
  updated_at: z.string(),
});

export const storedChatMessageSchema = z.object({
  id: z.number(),
  role: z.enum(["user", "assistant"]),
  content: z.string(),
  thinking: z.string().nullable().optional(),
  input_tokens: z.number().nullable().optional(),
  output_tokens: z.number().nullable().optional(),
  total_tokens: z.number().nullable().optional(),
});

export const storedChatSessionSchema = chatSessionDetailSchema.extend({
  messages: z.array(storedChatMessageSchema),
});

export const chatSessionSummariesSchema = z.array(chatSessionSummarySchema);

export type AssistantResponseMessage = z.infer<
  typeof assistantResponseMessageSchema
>;
export type AssistantStreamChunk = z.infer<typeof chatCompletionChunkSchema>;
export type TokenUsageResponse = z.infer<typeof tokenUsageSchema>;
